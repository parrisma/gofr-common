"""Shared runtime configuration helpers for OIDC verification and gofr-sec access."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _prefixed_name(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}" if prefix else suffix


def _first_env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return None


def _int_env(default: int, *names: str) -> int:
    value = _first_env_value(*names)
    return int(value) if value is not None else default


@dataclass(frozen=True)
class KeycloakVerifierSettings:
    """Environment-backed settings for Keycloak/OIDC token verification."""

    issuer_url: str | None = None
    audience: str | None = None
    request_timeout_seconds: int = 5
    jwks_cache_ttl_seconds: int = 300

    @classmethod
    def from_env(cls, prefix: str = "GOFR") -> "KeycloakVerifierSettings":
        return cls(
            issuer_url=_first_env_value(
                _prefixed_name(prefix, "KEYCLOAK_ISSUER_URL"),
                "GOFR_KEYCLOAK_ISSUER_URL",
            ),
            audience=_first_env_value(
                _prefixed_name(prefix, "KEYCLOAK_AUDIENCE"),
                "GOFR_KEYCLOAK_AUDIENCE",
            ),
            request_timeout_seconds=_int_env(
                5,
                _prefixed_name(prefix, "KEYCLOAK_REQUEST_TIMEOUT_S"),
                "GOFR_KEYCLOAK_REQUEST_TIMEOUT_S",
            ),
            jwks_cache_ttl_seconds=_int_env(
                300,
                _prefixed_name(prefix, "KEYCLOAK_JWKS_CACHE_TTL_S"),
                "GOFR_KEYCLOAK_JWKS_CACHE_TTL_S",
            ),
        )

    def is_configured(self) -> bool:
        return bool(self.issuer_url and self.audience)


@dataclass(frozen=True)
class GofrSecClientSettings:
    """Environment-backed settings for the shared gofr-sec runtime client."""

    base_url: str | None = None
    request_timeout_seconds: int = 5
    authz_cache_ttl_seconds: int = 30
    public_key_cache_ttl_seconds: int = 300

    @classmethod
    def from_env(cls, prefix: str = "GOFR") -> "GofrSecClientSettings":
        base_url = _first_env_value(
            _prefixed_name(prefix, "SEC_BASE_URL"),
            "GOFR_SEC_BASE_URL",
        )
        return cls(
            base_url=base_url.rstrip("/") if base_url else None,
            request_timeout_seconds=_int_env(
                5,
                _prefixed_name(prefix, "SEC_REQUEST_TIMEOUT_S"),
                "GOFR_SEC_REQUEST_TIMEOUT_S",
            ),
            authz_cache_ttl_seconds=_int_env(
                30,
                _prefixed_name(prefix, "SEC_AUTHZ_CACHE_TTL_S"),
                "GOFR_SEC_AUTHZ_CACHE_TTL_S",
            ),
            public_key_cache_ttl_seconds=_int_env(
                300,
                _prefixed_name(prefix, "SEC_PUBLIC_KEY_CACHE_TTL_S"),
                "GOFR_SEC_PUBLIC_KEY_CACHE_TTL_S",
            ),
        )

    def is_configured(self) -> bool:
        return bool(self.base_url)
