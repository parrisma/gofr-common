"""OpenID Connect discovery helpers for Keycloak-compatible issuers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from gofr_common.logger import Logger, create_logger

_WELL_KNOWN_SUFFIX = "/.well-known/openid-configuration"


class KeycloakDiscoveryError(Exception):
    """Raised when issuer discovery cannot be completed."""


class KeycloakDiscoveryConfigurationError(KeycloakDiscoveryError):
    """Raised when issuer metadata is missing required fields or is inconsistent."""


@dataclass(frozen=True)
class KeycloakDiscoveryDocument:
    """Typed subset of issuer metadata returned by OpenID discovery."""

    issuer: str
    jwks_uri: str
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    introspection_endpoint: str | None = None
    end_session_endpoint: str | None = None
    raw_claims: dict[str, Any] = field(default_factory=dict)


class KeycloakDiscoveryClient:
    """Resolve issuer metadata and JWKS locations for Keycloak-compatible issuers."""

    def __init__(
        self,
        timeout: float = 5.0,
        client: httpx.Client | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._owns_client = client is None
        self._logger = logger or create_logger(name="keycloak-discovery")

    @staticmethod
    def build_discovery_url(issuer_url: str) -> str:
        """Build the standard discovery URL for an issuer."""
        normalized = issuer_url.strip()
        if not normalized:
            raise ValueError("issuer_url is required")

        normalized = normalized.rstrip("/")
        if normalized.endswith(_WELL_KNOWN_SUFFIX):
            return normalized
        return f"{normalized}{_WELL_KNOWN_SUFFIX}"

    @staticmethod
    def expected_issuer(issuer_url: str) -> str:
        """Normalize the issuer URL that discovery is expected to return."""
        normalized = KeycloakDiscoveryClient.build_discovery_url(issuer_url)
        if normalized.endswith(_WELL_KNOWN_SUFFIX):
            normalized = normalized[: -len(_WELL_KNOWN_SUFFIX)]
        return normalized.rstrip("/")

    def discover(self, issuer_url: str) -> KeycloakDiscoveryDocument:
        """Fetch and validate OpenID issuer metadata for the given issuer URL."""
        discovery_url = self.build_discovery_url(issuer_url)
        expected_issuer = self.expected_issuer(issuer_url)

        try:
            response = self._client.get(
                discovery_url,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            self._logger.error(
                "Issuer discovery request failed",
                discovery_url=discovery_url,
                error=str(exc),
            )
            raise KeycloakDiscoveryError(
                f"Failed to fetch issuer metadata from {discovery_url}: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            self._logger.error(
                "Issuer discovery returned invalid JSON",
                discovery_url=discovery_url,
                error=str(exc),
            )
            raise KeycloakDiscoveryConfigurationError(
                f"Issuer metadata at {discovery_url} is not valid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise KeycloakDiscoveryConfigurationError(
                f"Issuer metadata at {discovery_url} must be a JSON object"
            )

        document = self._build_document(payload, expected_issuer)
        self._logger.debug(
            "Issuer discovery completed",
            issuer=document.issuer,
            jwks_uri=document.jwks_uri,
        )
        return document

    def close(self) -> None:
        """Close the underlying HTTP client if this instance created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "KeycloakDiscoveryClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @staticmethod
    def _normalize_url(value: str) -> str:
        return value.strip().rstrip("/")

    @classmethod
    def _build_document(
        cls,
        payload: dict[str, Any],
        expected_issuer: str,
    ) -> KeycloakDiscoveryDocument:
        issuer = payload.get("issuer")
        if not isinstance(issuer, str) or not issuer.strip():
            raise KeycloakDiscoveryConfigurationError("Issuer metadata missing 'issuer'")

        normalized_issuer = cls._normalize_url(issuer)
        if normalized_issuer != expected_issuer:
            raise KeycloakDiscoveryConfigurationError(
                "Issuer metadata issuer does not match the requested issuer"
            )

        jwks_uri = payload.get("jwks_uri")
        if not isinstance(jwks_uri, str) or not jwks_uri.strip():
            raise KeycloakDiscoveryConfigurationError("Issuer metadata missing 'jwks_uri'")

        return KeycloakDiscoveryDocument(
            issuer=normalized_issuer,
            jwks_uri=jwks_uri.strip(),
            authorization_endpoint=cls._optional_string(payload, "authorization_endpoint"),
            token_endpoint=cls._optional_string(payload, "token_endpoint"),
            userinfo_endpoint=cls._optional_string(payload, "userinfo_endpoint"),
            introspection_endpoint=cls._optional_string(payload, "introspection_endpoint"),
            end_session_endpoint=cls._optional_string(payload, "end_session_endpoint"),
            raw_claims=dict(payload),
        )

    @staticmethod
    def _optional_string(payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        return value.strip() if isinstance(value, str) and value.strip() else None
