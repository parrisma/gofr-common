"""JWKS fetch and cache helpers for OIDC-compatible identity providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from gofr_common.logger import Logger, create_logger


class JwksCacheError(Exception):
    """Raised when JWKS retrieval fails."""


class JwksCacheConfigurationError(JwksCacheError):
    """Raised when a JWKS document is invalid or incomplete."""


class JwksKeyNotFoundError(JwksCacheError):
    """Raised when a requested key id is not present in the JWKS document."""


@dataclass(frozen=True)
class JwksDocument:
    """Cached JSON Web Key Set document."""

    uri: str
    keys: tuple[dict[str, Any], ...]
    fetched_at: datetime


@dataclass
class _CacheEntry:
    document: JwksDocument
    expires_at: datetime


class JwksCache:
    """Fetch and cache JWKS documents with TTL-based refresh and retry behavior."""

    def __init__(
        self,
        ttl_seconds: int = 300,
        timeout: float = 5.0,
        max_retries: int = 1,
        client: httpx.Client | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_retries = max_retries
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._owns_client = client is None
        self._logger = logger or create_logger(name="jwks-cache")
        self._cache: dict[str, _CacheEntry] = {}

    def get_document(self, jwks_uri: str, force_refresh: bool = False) -> JwksDocument:
        """Return a JWKS document, using the cache until the entry expires."""
        if not force_refresh:
            cached = self._cache.get(jwks_uri)
            if cached is not None and self._now() < cached.expires_at:
                return cached.document

        document = self._fetch_document(jwks_uri)
        self._cache[jwks_uri] = _CacheEntry(
            document=document,
            expires_at=document.fetched_at + timedelta(seconds=self._ttl_seconds),
        )
        return document

    def refresh(self, jwks_uri: str) -> JwksDocument:
        """Force a fresh JWKS fetch and replace any cached entry."""
        return self.get_document(jwks_uri, force_refresh=True)

    def get_key(self, jwks_uri: str, kid: str) -> dict[str, Any]:
        """Return a JWK by `kid`, refreshing once if the cached set is stale."""
        normalized_kid = kid.strip()
        if not normalized_kid:
            raise ValueError("kid is required")

        document = self.get_document(jwks_uri)
        key = self._find_key(document, normalized_kid)
        if key is not None:
            return key

        document = self.refresh(jwks_uri)
        key = self._find_key(document, normalized_kid)
        if key is not None:
            return key

        raise JwksKeyNotFoundError(f"No JWK found for kid '{normalized_kid}'")

    def clear(self, jwks_uri: str | None = None) -> None:
        """Clear one cached JWKS entry or the entire cache."""
        if jwks_uri is None:
            self._cache.clear()
            return
        self._cache.pop(jwks_uri, None)

    def close(self) -> None:
        """Close the underlying HTTP client if this instance created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "JwksCache":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _fetch_document(self, jwks_uri: str) -> JwksDocument:
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.get(jwks_uri, headers={"Accept": "application/json"})
                response.raise_for_status()
                payload = response.json()
                return self._build_document(jwks_uri, payload)
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    self._logger.warning(
                        "JWKS fetch failed; retrying",
                        jwks_uri=jwks_uri,
                        attempt=attempt + 1,
                        error=str(exc),
                    )
                    continue
                self._logger.error(
                    "JWKS fetch failed",
                    jwks_uri=jwks_uri,
                    attempts=attempt + 1,
                    error=str(exc),
                )

        raise JwksCacheError(f"Failed to fetch JWKS from {jwks_uri}: {last_error}")

    @classmethod
    def _build_document(cls, jwks_uri: str, payload: Any) -> JwksDocument:
        if not isinstance(payload, dict):
            raise JwksCacheConfigurationError("JWKS response must be a JSON object")

        raw_keys = payload.get("keys")
        if not isinstance(raw_keys, list):
            raise JwksCacheConfigurationError("JWKS response missing 'keys' list")

        keys: list[dict[str, Any]] = []
        for item in raw_keys:
            if not isinstance(item, dict):
                raise JwksCacheConfigurationError("JWKS entries must be JSON objects")
            keys.append(dict(item))

        return JwksDocument(
            uri=jwks_uri,
            keys=tuple(keys),
            fetched_at=cls._now(),
        )

    @staticmethod
    def _find_key(document: JwksDocument, kid: str) -> dict[str, Any] | None:
        for key in document.keys:
            if key.get("kid") == kid:
                return dict(key)
        return None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
