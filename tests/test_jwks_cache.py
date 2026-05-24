"""Tests for JWKS caching helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import httpx
import pytest

from gofr_common.auth import (
    JwksCache,
    JwksCacheConfigurationError,
    JwksCacheError,
    JwksKeyNotFoundError,
)


@contextmanager
def jwks_cache(handler, ttl_seconds: int = 300) -> Iterator[JwksCache]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        yield JwksCache(client=http_client, ttl_seconds=ttl_seconds)
    finally:
        http_client.close()


class TestJwksCache:
    """Tests for TTL-based JWKS retrieval and lookup."""

    def test_get_document_fetches_and_caches(self):
        jwks_uri = "https://issuer.example/certs"
        call_count = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"keys": [{"kid": "key-1", "kty": "RSA"}]})

        with jwks_cache(handler) as cache:
            first = cache.get_document(jwks_uri)
            second = cache.get_document(jwks_uri)

        assert call_count == 1
        assert first.keys == second.keys
        assert first.uri == jwks_uri

    def test_get_document_refetches_after_expiry(self):
        jwks_uri = "https://issuer.example/certs"
        call_count = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"keys": [{"kid": f"key-{call_count}", "kty": "RSA"}]})

        with jwks_cache(handler, ttl_seconds=0) as cache:
            first = cache.get_document(jwks_uri)
            second = cache.get_document(jwks_uri)

        assert call_count == 2
        assert first.keys != second.keys

    def test_get_key_refreshes_once_when_kid_is_missing(self):
        jwks_uri = "https://issuer.example/certs"
        call_count = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"keys": [{"kid": "key-1", "kty": "RSA"}]})
            return httpx.Response(200, json={"keys": [{"kid": "key-2", "kty": "RSA"}]})

        with jwks_cache(handler) as cache:
            cache.get_document(jwks_uri)
            key = cache.get_key(jwks_uri, "key-2")

        assert call_count == 2
        assert key["kid"] == "key-2"

    def test_get_key_raises_when_kid_is_still_missing(self):
        jwks_uri = "https://issuer.example/certs"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"keys": [{"kid": "key-1", "kty": "RSA"}]})

        with jwks_cache(handler) as cache:
            with pytest.raises(JwksKeyNotFoundError, match="No JWK found"):
                cache.get_key(jwks_uri, "missing")

    def test_get_document_raises_for_http_errors(self):
        jwks_uri = "https://issuer.example/certs"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(502, json={"detail": "bad gateway"})

        with jwks_cache(handler) as cache:
            with pytest.raises(JwksCacheError, match="Failed to fetch JWKS"):
                cache.get_document(jwks_uri)

    def test_get_document_raises_for_invalid_jwks_shape(self):
        jwks_uri = "https://issuer.example/certs"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"keys": ["not-a-dict"]})

        with jwks_cache(handler) as cache:
            with pytest.raises(JwksCacheConfigurationError, match="JWKS entries must be JSON objects"):
                cache.get_document(jwks_uri)
