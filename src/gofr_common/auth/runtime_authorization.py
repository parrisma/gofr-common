"""Local verification plus remote yes-or-no authorization for runtime tokens."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .authz_cache import AuthorizationDecisionCache, AuthorizationDecisionCacheKey
from .runtime_config import GofrSecClientSettings
from .runtime_verifier import (
    RuntimeTokenVerificationError,
    RuntimeTokenVerifier,
    VerifiedRuntimeToken,
)
from .sec_client import (
    GofrSecClient,
    GofrSecClientError,
    RuntimeAuthorizationDecision,
    RuntimeAuthorizationRequest,
)


class RuntimeAuthorizationFlowError(Exception):
    """Raised when runtime authorization cannot be completed safely."""


@dataclass(frozen=True)
class RuntimeAuthorizationResult:
    """Runtime authorization result including verified token metadata."""

    decision: RuntimeAuthorizationDecision
    verified_token: VerifiedRuntimeToken
    from_cache: bool = False


class RuntimeAuthorizer:
    """Verify runtime JWTs locally, then ask gofr-sec for an allow-or-deny decision."""

    def __init__(
        self,
        verifier: RuntimeTokenVerifier,
        sec_client: GofrSecClient,
        cache: AuthorizationDecisionCache | None = None,
    ) -> None:
        self._verifier = verifier
        self._sec_client = sec_client
        self._cache = cache or AuthorizationDecisionCache()

    @classmethod
    def from_settings(
        cls,
        settings: GofrSecClientSettings,
        client: httpx.Client | None = None,
    ) -> "RuntimeAuthorizer":
        sec_client = GofrSecClient.from_settings(settings, client=client)
        verifier = RuntimeTokenVerifier(
            sec_client,
            public_key_cache_ttl_seconds=settings.public_key_cache_ttl_seconds,
            issuer=settings.token_issuer,
        )
        cache = AuthorizationDecisionCache(ttl_seconds=settings.authz_cache_ttl_seconds)
        return cls(verifier, sec_client, cache=cache)

    @classmethod
    def from_env(
        cls,
        prefix: str = "GOFR",
        client: httpx.Client | None = None,
    ) -> "RuntimeAuthorizer":
        return cls.from_settings(GofrSecClientSettings.from_env(prefix), client=client)

    def authorize(
        self,
        token: str,
        *,
        group: str | None = None,
        resource: str | None = None,
        correlation_id: str | None = None,
    ) -> RuntimeAuthorizationResult:
        verified_token = self._verifier.verify(token)
        cache_key = AuthorizationDecisionCacheKey(
            token_id=verified_token.token_id,
            group=group,
            resource=resource,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return RuntimeAuthorizationResult(
                decision=RuntimeAuthorizationDecision(allowed=cached.allowed),
                verified_token=verified_token,
                from_cache=True,
            )

        try:
            decision = self._sec_client.authorize(
                RuntimeAuthorizationRequest(
                    token_id=verified_token.token_id,
                    owner_sub=verified_token.owner_sub,
                    group=group,
                    resource=resource,
                    correlation_id=correlation_id,
                )
            )
        except GofrSecClientError as exc:
            raise RuntimeAuthorizationFlowError(f"Runtime authorization failed: {exc}") from exc

        self._cache.put(
            cache_key,
            allowed=decision.allowed,
            token_expires_at=verified_token.expires_at,
        )
        return RuntimeAuthorizationResult(
            decision=decision,
            verified_token=verified_token,
            from_cache=False,
        )

    def close(self) -> None:
        self._verifier.close()


def authorize_runtime_token(
    token: str,
    *,
    group: str | None = None,
    resource: str | None = None,
    correlation_id: str | None = None,
    authorizer: RuntimeAuthorizer | None = None,
    prefix: str = "GOFR",
) -> RuntimeAuthorizationResult:
    runtime_authorizer = authorizer or RuntimeAuthorizer.from_env(prefix)
    try:
        return runtime_authorizer.authorize(
            token,
            group=group,
            resource=resource,
            correlation_id=correlation_id,
        )
    finally:
        if authorizer is None:
            runtime_authorizer.close()


try:
    from fastapi import HTTPException, Request, Security, status
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

    _runtime_bearer = HTTPBearer(auto_error=False)

    def _require_runtime_group_impl(
        group_name: str,
        *,
        authorizer: RuntimeAuthorizer | None = None,
    ):
        def _require_runtime_group(
            request: Request,
            credentials: HTTPAuthorizationCredentials | None = Security(_runtime_bearer),
        ) -> VerifiedRuntimeToken:
            if credentials is None or not credentials.credentials.strip():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing bearer token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            runtime_authorizer = authorizer or getattr(request.app.state, "runtime_authorizer", None)
            if runtime_authorizer is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Runtime authorizer is not configured",
                )

            correlation_id = request.headers.get("X-Correlation-ID")
            try:
                result = runtime_authorizer.authorize(
                    credentials.credentials,
                    group=group_name,
                    correlation_id=correlation_id,
                )
            except RuntimeTokenVerificationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid runtime token: {exc}",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from exc
            except RuntimeAuthorizationFlowError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc

            if not result.decision.allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied",
                )
            return result.verified_token

        return _require_runtime_group

    require_runtime_group = _require_runtime_group_impl

except ImportError:
    def _require_runtime_group_unavailable(*_args, **_kwargs):
        raise ImportError("fastapi is required for runtime authorization dependencies")

    require_runtime_group = _require_runtime_group_unavailable
