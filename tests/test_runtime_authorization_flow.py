"""Tests for the local-verify plus remote-authorize runtime flow."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from gofr_common.auth import (
    GofrSecClientSettings,
    RuntimeAuthorizer,
    require_runtime_group,
)
from gofr_common.testing.security_fixtures import build_jwks_document, generate_rsa_key_material


def sign_runtime_token(key_material, *, issuer: str = "gofr-sec") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "jti": "token-1",
            "sub": "user-1",
            "iss": issuer,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=10)).timestamp()),
        },
        key_material.private_pem,
        algorithm="RS256",
        headers={"kid": key_material.kid},
    )


class TestRuntimeAuthorizer:
    def test_authorize_uses_remote_decision_and_then_cache(self):
        key_material = generate_rsa_key_material("runtime-auth")
        token = sign_runtime_token(key_material)
        settings = GofrSecClientSettings(
            base_url="https://sec.example",
            token_issuer="gofr-sec",
            authz_cache_ttl_seconds=30,
            public_key_cache_ttl_seconds=300,
        )
        key_requests = 0
        authorize_requests = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal key_requests, authorize_requests
            if request.url.path == "/v1/runtime/keys/public":
                key_requests += 1
                return httpx.Response(200, json=build_jwks_document(key_material))
            if request.url.path == "/v1/runtime/authorize":
                authorize_requests += 1
                payload = json.loads(request.content.decode("utf-8"))
                assert payload == {
                    "token_id": "token-1",
                    "owner_sub": "user-1",
                    "group": "plot.read",
                }
                return httpx.Response(200, json={"allowed": True})
            return httpx.Response(404)

        http_client = httpx.Client(
            base_url=settings.base_url,
            transport=httpx.MockTransport(handler),
        )
        authorizer = RuntimeAuthorizer.from_settings(settings, client=http_client)
        try:
            first = authorizer.authorize(token, group="plot.read", correlation_id="corr-1")
            second = authorizer.authorize(token, group="plot.read", correlation_id="corr-2")
        finally:
            authorizer.close()

        assert first.decision.allowed is True
        assert first.from_cache is False
        assert second.decision.allowed is True
        assert second.from_cache is True
        assert key_requests == 1
        assert authorize_requests == 1

    def test_require_runtime_group_works_with_fastapi_dependency(self):
        key_material = generate_rsa_key_material("runtime-fastapi")
        token = sign_runtime_token(key_material)
        settings = GofrSecClientSettings(base_url="https://sec.example", token_issuer="gofr-sec")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/runtime/keys/public":
                return httpx.Response(200, json=build_jwks_document(key_material))
            if request.url.path == "/v1/runtime/authorize":
                return httpx.Response(200, json={"allowed": True})
            return httpx.Response(404)

        http_client = httpx.Client(
            base_url=settings.base_url,
            transport=httpx.MockTransport(handler),
        )
        authorizer = RuntimeAuthorizer.from_settings(settings, client=http_client)

        app = FastAPI()
        app.state.runtime_authorizer = authorizer

        @app.get("/protected")
        def protected_endpoint(_token=Depends(require_runtime_group("plot.read"))):
            return {"allowed": True}

        try:
            with TestClient(app) as client:
                response = client.get(
                    "/protected",
                    headers={"Authorization": f"Bearer {token}"},
                )
        finally:
            authorizer.close()

        assert response.status_code == 200
        assert response.json() == {"allowed": True}
