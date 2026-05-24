"""Verification of gofr-sec runtime tokens using published public keys."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt

from gofr_common.logger import Logger, create_logger

from .runtime_config import GofrSecClientSettings
from .sec_client import GofrSecClient


class RuntimeTokenVerificationError(Exception):
    """Raised when a gofr-sec runtime token cannot be verified."""


@dataclass(frozen=True)
class VerifiedRuntimeToken:
    """Verified claims extracted from a gofr-sec runtime token."""

    token_id: str
    owner_sub: str
    issuer: str
    expires_at: datetime
    issued_at: datetime | None = None
    not_before: datetime | None = None
    claims: dict[str, Any] = field(default_factory=dict)


class RuntimeTokenVerifier:
    """Verify gofr-sec runtime JWTs against the published runtime key set."""

    def __init__(
        self,
        sec_client: GofrSecClient,
        *,
        public_key_cache_ttl_seconds: int = 300,
        issuer: str = "gofr-sec",
        algorithms: tuple[str, ...] = ("RS256",),
        leeway_seconds: int = 0,
        logger: Logger | None = None,
    ) -> None:
        self._sec_client = sec_client
        self._ttl_seconds = public_key_cache_ttl_seconds
        self._issuer = issuer
        self._algorithms = algorithms
        self._leeway_seconds = leeway_seconds
        self._logger = logger or create_logger(name="runtime-token-verifier")
        self._cached_document: dict[str, Any] | None = None
        self._cached_until: datetime | None = None

    @classmethod
    def from_settings(
        cls,
        settings: GofrSecClientSettings,
        client: httpx.Client | None = None,
        logger: Logger | None = None,
    ) -> "RuntimeTokenVerifier":
        sec_client = GofrSecClient.from_settings(settings, client=client, logger=logger)
        return cls(
            sec_client,
            public_key_cache_ttl_seconds=settings.public_key_cache_ttl_seconds,
            issuer=settings.token_issuer,
            logger=logger,
        )

    @classmethod
    def from_env(
        cls,
        prefix: str = "GOFR",
        client: httpx.Client | None = None,
        logger: Logger | None = None,
    ) -> "RuntimeTokenVerifier":
        return cls.from_settings(GofrSecClientSettings.from_env(prefix), client=client, logger=logger)

    def verify(self, token: str, issuer: str | None = None) -> VerifiedRuntimeToken:
        if not token.strip():
            raise RuntimeTokenVerificationError("Runtime token is required")

        header = self._get_token_header(token)
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid.strip():
            raise RuntimeTokenVerificationError("Runtime token header missing 'kid'")

        resolved_issuer = issuer or self._issuer
        try:
            payload = self._decode_token(token, kid=kid, issuer=resolved_issuer)
        except jwt.PyJWTError as exc:
            self._logger.error(
                "Runtime token verification failed",
                issuer=resolved_issuer,
                kid=kid,
                error=str(exc),
            )
            raise RuntimeTokenVerificationError(f"Runtime token verification failed: {exc}") from exc

        return self._build_verified_token(payload)

    def close(self) -> None:
        self._sec_client.close()

    def __enter__(self) -> "RuntimeTokenVerifier":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _decode_token(self, token: str, *, kid: str, issuer: str) -> dict[str, Any]:
        key = self._resolve_key(kid, refresh=False)
        try:
            return self._decode_with_key(token, key=key, issuer=issuer)
        except jwt.InvalidSignatureError:
            refreshed_key = self._resolve_key(kid, refresh=True)
            return self._decode_with_key(token, key=refreshed_key, issuer=issuer)

    def _resolve_key(self, kid: str, *, refresh: bool) -> Any:
        document = self._get_public_key_document(refresh=refresh)
        for key_data in document.get("keys", []):
            if isinstance(key_data, dict) and key_data.get("kid") == kid:
                return jwt.PyJWK.from_dict(key_data).key

        if refresh:
            raise RuntimeTokenVerificationError(f"Runtime key '{kid}' not found")
        return self._resolve_key(kid, refresh=True)

    def _get_public_key_document(self, *, refresh: bool) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        if (
            not refresh
            and self._cached_document is not None
            and self._cached_until is not None
            and now < self._cached_until
        ):
            return self._cached_document

        document = self._sec_client.get_public_key_document()
        keys = document.get("keys")
        if not isinstance(keys, list) or not all(isinstance(item, dict) for item in keys):
            raise RuntimeTokenVerificationError("Runtime key document missing 'keys' list")

        self._cached_document = document
        self._cached_until = now + timedelta(seconds=self._ttl_seconds)
        return document

    def _decode_with_key(self, token: str, *, key: Any, issuer: str) -> dict[str, Any]:
        return jwt.decode(
            token,
            key=key,
            algorithms=list(self._algorithms),
            issuer=issuer,
            options={"require": ["exp", "iss", "sub", "jti"], "verify_aud": False},
            leeway=self._leeway_seconds,
        )

    @staticmethod
    def _get_token_header(token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        if not isinstance(header, dict):
            raise RuntimeTokenVerificationError("Runtime token header is invalid")
        return header

    @classmethod
    def _build_verified_token(cls, payload: dict[str, Any]) -> VerifiedRuntimeToken:
        token_id = payload.get("jti")
        owner_sub = payload.get("sub")
        issuer = payload.get("iss")
        if not isinstance(token_id, str) or not token_id.strip():
            raise RuntimeTokenVerificationError("Runtime token missing 'jti' claim")
        if not isinstance(owner_sub, str) or not owner_sub.strip():
            raise RuntimeTokenVerificationError("Runtime token missing 'sub' claim")
        if not isinstance(issuer, str) or not issuer.strip():
            raise RuntimeTokenVerificationError("Runtime token missing 'iss' claim")

        return VerifiedRuntimeToken(
            token_id=token_id,
            owner_sub=owner_sub,
            issuer=issuer,
            expires_at=cls._coerce_timestamp(payload.get("exp"), claim_name="exp"),
            issued_at=cls._coerce_optional_timestamp(payload.get("iat"), claim_name="iat"),
            not_before=cls._coerce_optional_timestamp(payload.get("nbf"), claim_name="nbf"),
            claims=dict(payload),
        )

    @staticmethod
    def _coerce_timestamp(value: Any, *, claim_name: str) -> datetime:
        if not isinstance(value, int):
            raise RuntimeTokenVerificationError(f"Runtime token missing '{claim_name}' claim")
        return datetime.fromtimestamp(value, tz=timezone.utc)

    @classmethod
    def _coerce_optional_timestamp(cls, value: Any, *, claim_name: str) -> datetime | None:
        if value is None:
            return None
        return cls._coerce_timestamp(value, claim_name=claim_name)
