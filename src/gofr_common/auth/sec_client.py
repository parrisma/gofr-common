"""Shared runtime client for the gofr-sec authorization surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from gofr_common.logger import Logger, create_logger

from .runtime_config import GofrSecClientSettings


class GofrSecClientError(Exception):
    """Base error raised by the shared gofr-sec client."""


class GofrSecClientTransportError(GofrSecClientError):
    """Raised when the client cannot reach gofr-sec."""


class GofrSecClientResponseError(GofrSecClientError):
    """Raised when gofr-sec returns an invalid or unexpected response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class RuntimeAuthorizationRequest:
    """Request payload for gofr-sec runtime authorization checks."""

    token_id: str
    owner_sub: str
    group: str | None = None
    resource: str | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        token_id = self.token_id.strip()
        owner_sub = self.owner_sub.strip()
        group = self.group.strip() if self.group and self.group.strip() else None
        resource = self.resource.strip() if self.resource and self.resource.strip() else None
        correlation_id = (
            self.correlation_id.strip()
            if self.correlation_id and self.correlation_id.strip()
            else None
        )

        if not token_id:
            raise ValueError("token_id is required")
        if not owner_sub:
            raise ValueError("owner_sub is required")
        if not group and not resource:
            raise ValueError("either group or resource must be provided")

        object.__setattr__(self, "token_id", token_id)
        object.__setattr__(self, "owner_sub", owner_sub)
        object.__setattr__(self, "group", group)
        object.__setattr__(self, "resource", resource)
        object.__setattr__(self, "correlation_id", correlation_id)

    def to_payload(self) -> dict[str, str]:
        payload = {
            "token_id": self.token_id,
            "owner_sub": self.owner_sub,
        }
        if self.group is not None:
            payload["group"] = self.group
        if self.resource is not None:
            payload["resource"] = self.resource
        return payload

    def to_headers(self) -> dict[str, str]:
        if self.correlation_id is None:
            return {}
        return {"X-Correlation-ID": self.correlation_id}


@dataclass(frozen=True)
class RuntimeAuthorizationDecision:
    """Yes-or-no runtime authorization decision returned by gofr-sec."""

    allowed: bool


class GofrSecClient:
    """Small shared client for gofr-sec runtime authorization endpoints."""

    def __init__(
        self,
        settings: GofrSecClientSettings | None = None,
        client: httpx.Client | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._settings = settings or GofrSecClientSettings()
        self._logger = logger or create_logger(name="gofr-sec-client")
        self._owns_client = client is None

        if client is not None:
            self._client = client
        else:
            if not self._settings.is_configured():
                raise ValueError("gofr-sec client base_url is required")
            self._client = httpx.Client(
                base_url=str(self._settings.base_url),
                timeout=self._settings.request_timeout_seconds,
                follow_redirects=True,
            )

    @classmethod
    def from_settings(
        cls,
        settings: GofrSecClientSettings,
        client: httpx.Client | None = None,
        logger: Logger | None = None,
    ) -> "GofrSecClient":
        return cls(settings=settings, client=client, logger=logger)

    @classmethod
    def from_env(
        cls,
        prefix: str = "GOFR",
        client: httpx.Client | None = None,
        logger: Logger | None = None,
    ) -> "GofrSecClient":
        return cls.from_settings(GofrSecClientSettings.from_env(prefix), client=client, logger=logger)

    def get_public_key_document(self) -> dict[str, Any]:
        """Fetch the public verification key document from gofr-sec."""
        return self._request_json("GET", "/v1/runtime/keys/public")

    def authorize(self, request: RuntimeAuthorizationRequest) -> RuntimeAuthorizationDecision:
        """Request a yes-or-no runtime authorization decision from gofr-sec."""
        payload = self._request_json(
            "POST",
            "/v1/runtime/authorize",
            json_body=request.to_payload(),
            headers=request.to_headers(),
        )
        allowed = payload.get("allowed")
        if not isinstance(allowed, bool):
            raise GofrSecClientResponseError(
                "gofr-sec authorize response must contain a boolean 'allowed' field"
            )
        return RuntimeAuthorizationDecision(allowed=allowed)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "GofrSecClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, json=json_body, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._logger.error(
                "gofr-sec returned an error response",
                method=method,
                path=path,
                status_code=exc.response.status_code,
                error=str(exc),
            )
            raise GofrSecClientResponseError(
                f"gofr-sec returned HTTP {exc.response.status_code} for {path}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            self._logger.error(
                "gofr-sec request failed",
                method=method,
                path=path,
                error=str(exc),
            )
            raise GofrSecClientTransportError(
                f"Failed to reach gofr-sec for {path}: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise GofrSecClientResponseError(
                f"gofr-sec returned invalid JSON for {path}",
                status_code=response.status_code,
            ) from exc

        if not isinstance(payload, dict):
            raise GofrSecClientResponseError(
                f"gofr-sec returned an unexpected payload for {path}",
                status_code=response.status_code,
            )
        return payload
