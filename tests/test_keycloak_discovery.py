"""Tests for Keycloak-compatible issuer discovery helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import httpx
import pytest

from gofr_common.auth import (
    KeycloakDiscoveryClient,
    KeycloakDiscoveryConfigurationError,
    KeycloakDiscoveryDocument,
    KeycloakDiscoveryError,
)


@contextmanager
def discovery_client(handler) -> Iterator[KeycloakDiscoveryClient]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        yield KeycloakDiscoveryClient(client=http_client)
    finally:
        http_client.close()


class TestKeycloakDiscoveryClient:
    """Tests for OpenID discovery against Keycloak-compatible issuers."""

    def test_build_discovery_url(self):
        issuer = "https://keycloak.example/realms/gofr"
        expected = f"{issuer}/.well-known/openid-configuration"

        assert KeycloakDiscoveryClient.build_discovery_url(issuer) == expected
        assert KeycloakDiscoveryClient.build_discovery_url(f"{issuer}/") == expected
        assert KeycloakDiscoveryClient.build_discovery_url(expected) == expected

    def test_discover_returns_typed_document(self):
        issuer = "https://keycloak.example/realms/gofr"
        metadata = {
            "issuer": issuer,
            "jwks_uri": f"{issuer}/protocol/openid-connect/certs",
            "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
            "token_endpoint": f"{issuer}/protocol/openid-connect/token",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.headers["Accept"] == "application/json"
            assert str(request.url) == f"{issuer}/.well-known/openid-configuration"
            return httpx.Response(200, json=metadata)

        with discovery_client(handler) as client:
            document = client.discover(issuer)

        assert document == KeycloakDiscoveryDocument(
            issuer=issuer,
            jwks_uri=metadata["jwks_uri"],
            authorization_endpoint=metadata["authorization_endpoint"],
            token_endpoint=metadata["token_endpoint"],
            raw_claims=metadata,
        )

    def test_discover_normalizes_trailing_slash(self):
        issuer = "https://keycloak.example/realms/gofr"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "issuer": issuer,
                    "jwks_uri": f"{issuer}/protocol/openid-connect/certs",
                },
            )

        with discovery_client(handler) as client:
            document = client.discover(f"{issuer}/")

        assert document.issuer == issuer

    def test_discover_raises_for_http_failures(self):
        issuer = "https://keycloak.example/realms/gofr"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"detail": "temporarily unavailable"})

        with discovery_client(handler) as client:
            with pytest.raises(KeycloakDiscoveryError, match="Failed to fetch issuer metadata"):
                client.discover(issuer)

    def test_discover_raises_when_required_fields_are_missing(self):
        issuer = "https://keycloak.example/realms/gofr"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"issuer": issuer})

        with discovery_client(handler) as client:
            with pytest.raises(
                KeycloakDiscoveryConfigurationError,
                match="missing 'jwks_uri'",
            ):
                client.discover(issuer)

    def test_discover_raises_on_issuer_mismatch(self):
        issuer = "https://keycloak.example/realms/gofr"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "issuer": "https://other.example/realms/elsewhere",
                    "jwks_uri": "https://other.example/certs",
                },
            )

        with discovery_client(handler) as client:
            with pytest.raises(
                KeycloakDiscoveryConfigurationError,
                match="does not match the requested issuer",
            ):
                client.discover(issuer)
