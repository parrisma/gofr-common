"""Tests for gofr-sec runtime token verification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from gofr_common.auth import (
    GofrSecClientSettings,
    RuntimeTokenVerificationError,
    RuntimeTokenVerifier,
)
from gofr_common.testing.security_fixtures import build_jwks_document, generate_rsa_key_material


def sign_runtime_token(
    key_material,
    *,
    issuer: str = "gofr-sec",
    subject: str = "user-123",
    token_id: str = "token-123",
    include_kid: bool = True,
) -> str:
    now = datetime.now(timezone.utc)
    headers = {"kid": key_material.kid} if include_kid else None
    return jwt.encode(
        {
            "jti": token_id,
            "sub": subject,
            "iss": issuer,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
        },
        key_material.private_pem,
        algorithm="RS256",
        headers=headers,
    )


def verifier_for(handler, settings: GofrSecClientSettings) -> RuntimeTokenVerifier:
    http_client = httpx.Client(
        base_url=settings.base_url or "https://sec.example",
        transport=httpx.MockTransport(handler),
    )
    return RuntimeTokenVerifier.from_settings(settings, client=http_client)


class TestRuntimeTokenVerifier:
    def test_verify_returns_verified_runtime_token(self):
        key_material = generate_rsa_key_material("runtime-key")
        token = sign_runtime_token(key_material, token_id="token-abc", subject="user-9")
        settings = GofrSecClientSettings(base_url="https://sec.example", token_issuer="gofr-sec")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/runtime/keys/public"
            return httpx.Response(200, json=build_jwks_document(key_material))

        verifier = verifier_for(handler, settings)
        try:
            verified = verifier.verify(token)
        finally:
            verifier.close()

        assert verified.token_id == "token-abc"
        assert verified.owner_sub == "user-9"
        assert verified.issuer == "gofr-sec"
        assert verified.expires_at > verified.issued_at

    def test_verify_rejects_missing_kid(self):
        key_material = generate_rsa_key_material("runtime-key")
        token = sign_runtime_token(key_material, include_kid=False)
        settings = GofrSecClientSettings(base_url="https://sec.example", token_issuer="gofr-sec")

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=build_jwks_document(key_material))

        verifier = verifier_for(handler, settings)
        try:
            with pytest.raises(RuntimeTokenVerificationError, match="missing 'kid'"):
                verifier.verify(token)
        finally:
            verifier.close()

    def test_verify_refreshes_public_key_document_after_signature_failure(self):
        stale_key = generate_rsa_key_material("shared-kid")
        current_key = generate_rsa_key_material("shared-kid")
        token = sign_runtime_token(current_key)
        settings = GofrSecClientSettings(base_url="https://sec.example", token_issuer="gofr-sec")
        key_requests = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal key_requests
            assert request.url.path == "/v1/runtime/keys/public"
            key_requests += 1
            if key_requests == 1:
                return httpx.Response(200, json=build_jwks_document(stale_key))
            return httpx.Response(200, json=build_jwks_document(current_key))

        verifier = verifier_for(handler, settings)
        try:
            verified = verifier.verify(token)
        finally:
            verifier.close()

        assert key_requests == 2
        assert verified.owner_sub == "user-123"
