"""Reusable pytest fixtures and helpers for OIDC/JWKS/security tests."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@dataclass(frozen=True)
class RsaKeyMaterial:
    """Generated RSA keypair material plus the matching public JWK."""

    kid: str
    private_pem: bytes
    jwk: dict[str, str]


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_rsa_key_material(kid: str = "test-key") -> RsaKeyMaterial:
    """Generate RSA key material for signing and JWK-based verification tests."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_numbers = private_key.public_key().public_numbers()
    jwk = {
        "kid": kid,
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "n": _b64url_uint(public_numbers.n),
        "e": _b64url_uint(public_numbers.e),
    }
    return RsaKeyMaterial(kid=kid, private_pem=private_pem, jwk=jwk)


def build_jwks_document(*key_materials: RsaKeyMaterial) -> dict[str, Any]:
    """Build a JWKS document from one or more generated RSA key fixtures."""
    return {"keys": [material.jwk for material in key_materials]}


def build_issuer_metadata_document(
    issuer_url: str,
    jwks_uri: str | None = None,
) -> dict[str, Any]:
    """Build a minimal OpenID discovery document for tests."""
    normalized_issuer = issuer_url.rstrip("/")
    return {
        "issuer": normalized_issuer,
        "jwks_uri": jwks_uri or f"{normalized_issuer}/protocol/openid-connect/certs",
    }


def sign_access_token(
    key_material: RsaKeyMaterial,
    *,
    issuer_url: str,
    audience: str = "gofr-api",
    subject: str = "user-123",
    expires_in_seconds: int = 1800,
    include_kid: bool = True,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed RS256 access token for OIDC verification tests."""
    now = datetime.now(timezone.utc)
    claims = {
        "sub": subject,
        "iss": issuer_url.rstrip("/"),
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
    }
    if additional_claims:
        claims.update(additional_claims)

    headers = {"kid": key_material.kid} if include_kid else None
    return jwt.encode(claims, key_material.private_pem, algorithm="RS256", headers=headers)


def build_oidc_mock_handler(
    issuer_metadata_document: dict[str, Any],
    jwks_document: dict[str, Any],
) -> Callable[[httpx.Request], httpx.Response]:
    """Build a MockTransport handler that serves discovery and JWKS documents."""
    issuer = str(issuer_metadata_document["issuer"]).rstrip("/")
    jwks_uri = str(issuer_metadata_document["jwks_uri"])
    discovery_url = f"{issuer}/.well-known/openid-configuration"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == discovery_url:
            return httpx.Response(200, json=issuer_metadata_document)
        if str(request.url) == jwks_uri:
            return httpx.Response(200, json=jwks_document)
        return httpx.Response(404)

    return handler


@pytest.fixture
def issuer_url() -> str:
    return "https://keycloak.example/realms/gofr"


@pytest.fixture
def jwks_uri(issuer_url: str) -> str:
    return f"{issuer_url}/protocol/openid-connect/certs"


@pytest.fixture
def rsa_key_material() -> RsaKeyMaterial:
    return generate_rsa_key_material()


@pytest.fixture
def issuer_metadata_document(issuer_url: str, jwks_uri: str) -> dict[str, Any]:
    return build_issuer_metadata_document(issuer_url, jwks_uri=jwks_uri)


@pytest.fixture
def jwks_document(rsa_key_material: RsaKeyMaterial) -> dict[str, Any]:
    return build_jwks_document(rsa_key_material)


@pytest.fixture
def signed_access_token(rsa_key_material: RsaKeyMaterial, issuer_url: str) -> str:
    return sign_access_token(rsa_key_material, issuer_url=issuer_url)


@pytest.fixture
def oidc_mock_handler(
    issuer_metadata_document: dict[str, Any],
    jwks_document: dict[str, Any],
) -> Callable[[httpx.Request], httpx.Response]:
    return build_oidc_mock_handler(issuer_metadata_document, jwks_document)
