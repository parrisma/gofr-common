"""OIDC access-token verification built on issuer discovery and cached JWKS lookup."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import jwt

from gofr_common.logger import Logger, create_logger

from .jwks_cache import JwksCache
from .keycloak_discovery import KeycloakDiscoveryClient
from .runtime_config import KeycloakVerifierSettings


class AccessTokenVerificationError(Exception):
    """Raised when an OIDC access token cannot be verified."""


@dataclass(frozen=True)
class VerifiedIdentity:
    """Verified identity extracted from an access token."""

    subject: str
    issuer: str
    audience: tuple[str, ...]
    expires_at: datetime
    issued_at: datetime | None = None
    not_before: datetime | None = None
    claims: dict[str, Any] = field(default_factory=dict)


class AccessTokenVerifier:
    """Verify OIDC access tokens against discovered issuer metadata and cached JWKS."""

    def __init__(
        self,
        discovery_client: KeycloakDiscoveryClient | None = None,
        jwks_cache: JwksCache | None = None,
        algorithms: tuple[str, ...] = ("RS256",),
        leeway_seconds: int = 0,
        issuer_url: str | None = None,
        audience: str | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._discovery_client = discovery_client or KeycloakDiscoveryClient()
        self._owns_discovery_client = discovery_client is None
        self._jwks_cache = jwks_cache or JwksCache()
        self._owns_jwks_cache = jwks_cache is None
        self._algorithms = algorithms
        self._leeway_seconds = leeway_seconds
        self._issuer_url = issuer_url
        self._audience = audience
        self._logger = logger or create_logger(name="oidc-verifier")

    @classmethod
    def from_settings(
        cls,
        settings: KeycloakVerifierSettings,
        client: httpx.Client | None = None,
        logger: Logger | None = None,
    ) -> "AccessTokenVerifier":
        discovery_client = KeycloakDiscoveryClient(
            timeout=settings.request_timeout_seconds,
            client=client,
        )
        jwks_cache = JwksCache(
            ttl_seconds=settings.jwks_cache_ttl_seconds,
            timeout=settings.request_timeout_seconds,
            client=client,
        )
        return cls(
            discovery_client=discovery_client,
            jwks_cache=jwks_cache,
            issuer_url=settings.issuer_url,
            audience=settings.audience,
            logger=logger,
        )

    def verify(
        self,
        token: str,
        issuer_url: str | None = None,
        audience: str | None = None,
    ) -> VerifiedIdentity:
        """Verify an access token and return a typed identity model."""
        if not token.strip():
            raise AccessTokenVerificationError("Access token is required")

        resolved_issuer = issuer_url or self._issuer_url
        resolved_audience = audience if audience is not None else self._audience
        if not resolved_issuer:
            raise AccessTokenVerificationError("issuer_url is required for token verification")

        discovery = self._discovery_client.discover(resolved_issuer)
        header = self._get_token_header(token)
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid.strip():
            raise AccessTokenVerificationError("Access token header missing 'kid'")

        try:
            payload = self._decode_token(
                token,
                jwks_uri=discovery.jwks_uri,
                issuer=discovery.issuer,
                audience=resolved_audience,
                kid=kid,
            )
        except jwt.PyJWTError as exc:
            self._logger.error(
                "Access token verification failed",
                issuer=discovery.issuer,
                kid=kid,
                error=str(exc),
            )
            raise AccessTokenVerificationError(f"Access token verification failed: {exc}") from exc

        identity = self._build_identity(payload)
        self._logger.debug(
            "Access token verified",
            issuer=identity.issuer,
            subject=identity.subject,
            audience=list(identity.audience),
        )
        return identity

    def close(self) -> None:
        """Close any owned discovery/cache dependencies."""
        if self._owns_discovery_client:
            self._discovery_client.close()
        if self._owns_jwks_cache:
            self._jwks_cache.close()

    def __enter__(self) -> "AccessTokenVerifier":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _decode_token(
        self,
        token: str,
        *,
        jwks_uri: str,
        issuer: str,
        audience: str | None,
        kid: str,
    ) -> dict[str, Any]:
        key = self._jwk_to_public_key(self._jwks_cache.get_key(jwks_uri, kid))
        try:
            return self._decode_with_key(token, key=key, issuer=issuer, audience=audience)
        except jwt.InvalidSignatureError:
            self._jwks_cache.refresh(jwks_uri)
            refreshed_jwk = self._jwks_cache.get_key(jwks_uri, kid)
            refreshed_key = self._jwk_to_public_key(refreshed_jwk)
            return self._decode_with_key(token, key=refreshed_key, issuer=issuer, audience=audience)

    def _decode_with_key(
        self,
        token: str,
        *,
        key: Any,
        issuer: str,
        audience: str | None,
    ) -> dict[str, Any]:
        options = {
            "require": ["exp", "iss", "sub"],
            "verify_aud": audience is not None,
        }
        return jwt.decode(
            token,
            key=key,
            algorithms=list(self._algorithms),
            audience=audience,
            issuer=issuer,
            options=options,
            leeway=self._leeway_seconds,
        )

    @staticmethod
    def _get_token_header(token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        if not isinstance(header, dict):
            raise AccessTokenVerificationError("Access token header is invalid")
        return header

    @staticmethod
    def _jwk_to_public_key(jwk: dict[str, Any]) -> Any:
        return jwt.PyJWK.from_dict(jwk).key

    @classmethod
    def _build_identity(cls, payload: dict[str, Any]) -> VerifiedIdentity:
        subject = payload.get("sub")
        issuer = payload.get("iss")
        if not isinstance(subject, str) or not subject.strip():
            raise AccessTokenVerificationError("Access token missing 'sub' claim")
        if not isinstance(issuer, str) or not issuer.strip():
            raise AccessTokenVerificationError("Access token missing 'iss' claim")

        exp = cls._coerce_timestamp(payload.get("exp"), claim_name="exp")
        iat_value = payload.get("iat")
        nbf_value = payload.get("nbf")

        return VerifiedIdentity(
            subject=subject,
            issuer=issuer,
            audience=cls._normalize_audience(payload.get("aud")),
            expires_at=exp,
            issued_at=cls._coerce_optional_timestamp(iat_value, claim_name="iat"),
            not_before=cls._coerce_optional_timestamp(nbf_value, claim_name="nbf"),
            claims=dict(payload),
        )

    @staticmethod
    def _normalize_audience(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return tuple(value)
        raise AccessTokenVerificationError("Access token 'aud' claim has invalid format")

    @staticmethod
    def _coerce_timestamp(value: Any, *, claim_name: str) -> datetime:
        if not isinstance(value, int):
            raise AccessTokenVerificationError(f"Access token missing '{claim_name}' claim")
        return datetime.fromtimestamp(value, tz=timezone.utc)

    @classmethod
    def _coerce_optional_timestamp(cls, value: Any, *, claim_name: str) -> datetime | None:
        if value is None:
            return None
        return cls._coerce_timestamp(value, claim_name=claim_name)
