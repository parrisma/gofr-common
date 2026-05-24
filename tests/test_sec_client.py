"""Tests for shared gofr-sec runtime client and config helpers."""

from __future__ import annotations

import json

import httpx
import pytest

from gofr_common.auth import (
    GofrSecClient,
    GofrSecClientResponseError,
    GofrSecClientSettings,
    KeycloakVerifierSettings,
    RuntimeAuthorizationDecision,
    RuntimeAuthorizationRequest,
)


def client_for(handler, settings: GofrSecClientSettings) -> GofrSecClient:
    http_client = httpx.Client(
        base_url=settings.base_url or "https://sec.example",
        transport=httpx.MockTransport(handler),
    )
    return GofrSecClient.from_settings(settings, client=http_client)


class TestRuntimeSettings:
    """Tests for env-backed settings used by the shared runtime helpers."""

    def test_keycloak_verifier_settings_prefer_service_prefix(self, monkeypatch):
        monkeypatch.setenv("GOFR_KEYCLOAK_ISSUER_URL", "https://global.example/realms/global")
        monkeypatch.setenv("GOFR_KEYCLOAK_AUDIENCE", "global-audience")
        monkeypatch.setenv("GOFR_PLOT_KEYCLOAK_ISSUER_URL", "https://svc.example/realms/plot")
        monkeypatch.setenv("GOFR_PLOT_KEYCLOAK_AUDIENCE", "plot-audience")

        settings = KeycloakVerifierSettings.from_env("GOFR_PLOT")

        assert settings.issuer_url == "https://svc.example/realms/plot"
        assert settings.audience == "plot-audience"
        assert settings.is_configured() is True

    def test_gofr_sec_client_settings_fall_back_to_global_values(self, monkeypatch):
        monkeypatch.setenv("GOFR_SEC_BASE_URL", "https://sec.example/")
        monkeypatch.setenv("GOFR_SEC_TOKEN_ISSUER", "https://sec.example/issuer")
        monkeypatch.setenv("GOFR_SEC_REQUEST_TIMEOUT_S", "9")
        monkeypatch.setenv("GOFR_SEC_AUTHZ_CACHE_TTL_S", "45")
        monkeypatch.setenv("GOFR_SEC_PUBLIC_KEY_CACHE_TTL_S", "600")

        settings = GofrSecClientSettings.from_env("GOFR_PLOT")

        assert settings.base_url == "https://sec.example"
        assert settings.token_issuer == "https://sec.example/issuer"
        assert settings.request_timeout_seconds == 9
        assert settings.authz_cache_ttl_seconds == 45
        assert settings.public_key_cache_ttl_seconds == 600
        assert settings.is_configured() is True


class TestGofrSecClient:
    """Tests for the shared gofr-sec runtime client."""

    def test_get_public_key_document_uses_runtime_path(self, jwks_document):
        settings = GofrSecClientSettings(base_url="https://sec.example")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/v1/runtime/keys/public"
            return httpx.Response(200, json=jwks_document)

        client = client_for(handler, settings)
        try:
            document = client.get_public_key_document()
        finally:
            client.close()

        assert document == jwks_document

    def test_authorize_posts_expected_payload_and_header(self):
        settings = GofrSecClientSettings(base_url="https://sec.example")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path == "/v1/runtime/authorize"
            assert request.headers["X-Correlation-ID"] == "corr-123"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == {
                "token_id": "token-1",
                "owner_sub": "user-1",
                "group": "plot.read",
            }
            return httpx.Response(200, json={"allowed": False})

        request = RuntimeAuthorizationRequest(
            token_id="token-1",
            owner_sub="user-1",
            group="plot.read",
            correlation_id="corr-123",
        )

        client = client_for(handler, settings)
        try:
            decision = client.authorize(request)
        finally:
            client.close()

        assert decision == RuntimeAuthorizationDecision(allowed=False)

    def test_authorize_rejects_invalid_response_shape(self):
        settings = GofrSecClientSettings(base_url="https://sec.example")

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        client = client_for(handler, settings)
        try:
            with pytest.raises(GofrSecClientResponseError, match="boolean 'allowed' field"):
                client.authorize(
                    RuntimeAuthorizationRequest(
                        token_id="token-1",
                        owner_sub="user-1",
                        resource="plot:graph-1",
                    )
                )
        finally:
            client.close()

    def test_runtime_authorization_request_requires_group_or_resource(self):
        with pytest.raises(ValueError, match="exactly one of group or resource"):
            RuntimeAuthorizationRequest(token_id="token-1", owner_sub="user-1")

    def test_runtime_authorization_request_rejects_group_and_resource_together(self):
        with pytest.raises(ValueError, match="exactly one of group or resource"):
            RuntimeAuthorizationRequest(
                token_id="token-1",
                owner_sub="user-1",
                group="plot.read",
                resource="plot.read",
            )
