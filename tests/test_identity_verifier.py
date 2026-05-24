"""Tests for OIDC access-token verification."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import httpx
import pytest

from gofr_common.auth import (
    AccessTokenVerificationError,
    AccessTokenVerifier,
    KeycloakVerifierSettings,
)
from gofr_common.auth.jwks_cache import JwksCache
from gofr_common.auth.keycloak_discovery import KeycloakDiscoveryClient
from gofr_common.testing.security_fixtures import (
    build_jwks_document,
    build_oidc_mock_handler,
    generate_rsa_key_material,
    sign_access_token,
)


@contextmanager
def verifier_for(
    handler,
    settings: KeycloakVerifierSettings | None = None,
) -> Iterator[AccessTokenVerifier]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        if settings is None:
            yield AccessTokenVerifier(
                discovery_client=KeycloakDiscoveryClient(client=http_client),
                jwks_cache=JwksCache(client=http_client),
            )
        else:
            yield AccessTokenVerifier.from_settings(settings, client=http_client)
    finally:
        http_client.close()


class TestAccessTokenVerifier:
    """Tests for verification against discovered issuer metadata and JWKS."""

    def test_verify_returns_verified_identity(
        self,
        issuer_url,
        issuer_metadata_document,
        jwks_document,
        rsa_key_material,
    ):
        token = sign_access_token(rsa_key_material, issuer_url=issuer_url)

        with verifier_for(build_oidc_mock_handler(issuer_metadata_document, jwks_document)) as verifier:
            identity = verifier.verify(token, issuer_url, audience="gofr-api")

        assert identity.subject == "user-123"
        assert identity.issuer == issuer_url
        assert identity.audience == ("gofr-api",)
        assert identity.expires_at > identity.issued_at

    def test_verify_rejects_wrong_audience(
        self,
        issuer_url,
        issuer_metadata_document,
        jwks_document,
        rsa_key_material,
    ):
        token = sign_access_token(rsa_key_material, issuer_url=issuer_url, audience="gofr-api")

        with verifier_for(build_oidc_mock_handler(issuer_metadata_document, jwks_document)) as verifier:
            with pytest.raises(AccessTokenVerificationError, match="verification failed"):
                verifier.verify(token, issuer_url, audience="different-audience")

    def test_verify_rejects_missing_kid(
        self,
        issuer_url,
        issuer_metadata_document,
        jwks_document,
        rsa_key_material,
    ):
        token = sign_access_token(
            rsa_key_material,
            issuer_url=issuer_url,
            include_kid=False,
        )

        with verifier_for(build_oidc_mock_handler(issuer_metadata_document, jwks_document)) as verifier:
            with pytest.raises(AccessTokenVerificationError, match="missing 'kid'"):
                verifier.verify(token, issuer_url, audience="gofr-api")

    def test_verify_refreshes_jwks_after_signature_failure(self, issuer_url, issuer_metadata_document):
        stale_key = generate_rsa_key_material("shared-kid")
        current_key = generate_rsa_key_material("shared-kid")
        token = sign_access_token(current_key, issuer_url=issuer_url)
        jwks_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal jwks_calls
            discovery_handler = build_oidc_mock_handler(
                issuer_metadata_document,
                build_jwks_document(stale_key),
            )
            if str(request.url) == f"{issuer_url}/.well-known/openid-configuration":
                return discovery_handler(request)
            if str(request.url) == issuer_metadata_document["jwks_uri"]:
                jwks_calls += 1
                if jwks_calls == 1:
                    return httpx.Response(200, json=build_jwks_document(stale_key))
                return httpx.Response(200, json=build_jwks_document(current_key))
            return httpx.Response(404)

        with verifier_for(handler) as verifier:
            identity = verifier.verify(token, issuer_url, audience="gofr-api")

        assert jwks_calls == 2
        assert identity.subject == "user-123"

    def test_verifier_from_settings_uses_default_issuer_and_audience(
        self,
        issuer_url,
        issuer_metadata_document,
        jwks_document,
        rsa_key_material,
    ):
        settings = KeycloakVerifierSettings(
            issuer_url=issuer_url,
            audience="gofr-api",
            request_timeout_seconds=5,
            jwks_cache_ttl_seconds=300,
        )
        token = sign_access_token(rsa_key_material, issuer_url=issuer_url)

        with verifier_for(
            build_oidc_mock_handler(issuer_metadata_document, jwks_document),
            settings=settings,
        ) as verifier:
            identity = verifier.verify(token)

        assert identity.subject == "user-123"
