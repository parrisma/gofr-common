"""Tests for gofr_common.auth module."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gofr_common.auth import AuthService, TokenInfo


# ============================================================================
# Test TokenInfo dataclass
# ============================================================================


class TestTokenInfo:
    """Tests for the TokenInfo dataclass."""

    def test_token_info_creation(self):
        """Test creating a TokenInfo."""
        now = datetime.utcnow()
        expires = now + timedelta(days=30)
        
        info = TokenInfo(
            token="test-token",
            group="admin",
            expires_at=expires,
            issued_at=now,
        )
        
        assert info.token == "test-token"
        assert info.group == "admin"
        assert info.expires_at == expires
        assert info.issued_at == now


# ============================================================================
# Test AuthService initialization
# ============================================================================


class TestAuthServiceInit:
    """Tests for AuthService initialization."""

    def test_init_with_secret(self, tmp_path: Path):
        """Test initialization with explicit secret."""
        token_store = tmp_path / "tokens.json"
        auth = AuthService(
            secret_key="test-secret-key",
            token_store_path=str(token_store),
        )
        
        assert auth.secret_key == "test-secret-key"
        assert auth.token_store_path == token_store

    def test_init_with_env_var(self, tmp_path: Path):
        """Test initialization with environment variable."""
        token_store = tmp_path / "tokens.json"
        
        with patch.dict(os.environ, {"GOFR_TEST_JWT_SECRET": "env-secret"}):
            auth = AuthService(
                token_store_path=str(token_store),
                env_prefix="GOFR_TEST",
            )
            
            assert auth.secret_key == "env-secret"

    def test_init_auto_generates_secret(self, tmp_path: Path):
        """Test that secret is auto-generated when not provided."""
        token_store = tmp_path / "tokens.json"
        
        # Clear any existing env var
        with patch.dict(os.environ, {}, clear=True):
            auth = AuthService(
                token_store_path=str(token_store),
                env_prefix="GOFR_NONE",
            )
            
            assert auth.secret_key is not None
            assert len(auth.secret_key) == 64  # hex of 32 bytes

    def test_init_memory_mode(self):
        """Test initialization with in-memory token store."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        assert auth._use_memory_store is True
        assert auth.token_store_path is None
        assert auth.token_store == {}

    def test_init_loads_existing_store(self, tmp_path: Path):
        """Test that existing token store is loaded."""
        token_store = tmp_path / "tokens.json"
        token_store.write_text(json.dumps({
            "existing-token": {"group": "admin", "issued_at": "2024-01-01", "expires_at": "2024-12-31"}
        }))
        
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=str(token_store),
        )
        
        assert "existing-token" in auth.token_store

    def test_secret_fingerprint(self):
        """Test secret fingerprint generation."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        fingerprint = auth.get_secret_fingerprint()
        assert fingerprint.startswith("sha256:")
        assert len(fingerprint) == 19  # "sha256:" + 12 hex chars


# ============================================================================
# Test token creation
# ============================================================================


class TestTokenCreation:
    """Tests for token creation."""

    def test_create_token(self):
        """Test basic token creation."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        token = auth.create_token(group="admin")
        
        assert token is not None
        assert len(token) > 0
        assert token in auth.token_store
        assert auth.token_store[token]["group"] == "admin"

    def test_create_token_with_expiry(self):
        """Test token creation with custom expiry."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        token = auth.create_token(group="user", expires_in_seconds=3600)
        
        # Verify token is stored
        assert token in auth.token_store
        
        # Verify expiry is approximately 1 hour from now
        expires_at = datetime.fromisoformat(auth.token_store[token]["expires_at"])
        now = datetime.utcnow()
        diff = (expires_at - now).total_seconds()
        assert 3590 < diff < 3610  # Within 10 seconds of expected

    def test_create_token_with_fingerprint(self):
        """Test token creation with fingerprint."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        token = auth.create_token(
            group="admin",
            fingerprint="device-fingerprint-hash",
        )
        
        assert auth.token_store[token]["fingerprint"] == "device-fingerprint-hash"

    def test_create_token_with_jti(self):
        """Test token creation with token ID."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        token = auth.create_token(
            group="admin",
            token_id="unique-token-id",
        )
        
        assert auth.token_store[token]["jti"] == "unique-token-id"

    def test_create_token_saves_to_file(self, tmp_path: Path):
        """Test that token creation saves to file."""
        token_store = tmp_path / "tokens.json"
        
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=str(token_store),
        )
        
        token = auth.create_token(group="admin")
        
        # Read file and verify
        stored = json.loads(token_store.read_text())
        assert token in stored


# ============================================================================
# Test token verification
# ============================================================================


class TestTokenVerification:
    """Tests for token verification."""

    def test_verify_valid_token(self):
        """Test verifying a valid token."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        token = auth.create_token(group="admin")
        info = auth.verify_token(token)
        
        assert info.group == "admin"
        assert info.token == token

    def test_verify_expired_token(self):
        """Test that expired tokens are rejected."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        # Create token that expires in -1 seconds (already expired)
        token = auth.create_token(group="admin", expires_in_seconds=-1)
        
        with pytest.raises(ValueError, match="expired"):
            auth.verify_token(token)

    def test_verify_token_not_in_store(self):
        """Test that tokens not in store are rejected."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        # Create a valid JWT but don't add to store
        import jwt
        payload = {
            "group": "admin",
            "iat": int(datetime.utcnow().timestamp()),
            "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
        }
        token = jwt.encode(payload, "test-secret", algorithm="HS256")
        
        with pytest.raises(ValueError, match="not found in token store"):
            auth.verify_token(token)

    def test_verify_token_wrong_secret(self):
        """Test that tokens signed with wrong secret are rejected."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        # Create token with different secret
        import jwt
        payload = {
            "group": "admin",
            "iat": int(datetime.utcnow().timestamp()),
            "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        
        with pytest.raises(ValueError, match="Invalid token"):
            auth.verify_token(token)

    def test_verify_token_fingerprint_mismatch(self):
        """Test that fingerprint mismatch is detected."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        token = auth.create_token(
            group="admin",
            fingerprint="original-fingerprint",
        )
        
        with pytest.raises(ValueError, match="fingerprint mismatch"):
            auth.verify_token(token, fingerprint="different-fingerprint")

    def test_verify_token_stateless(self):
        """Test stateless verification (require_store=False)."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        # Create a valid JWT but don't add to store
        import jwt
        payload = {
            "group": "admin",
            "iat": int(datetime.utcnow().timestamp()),
            "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
        }
        token = jwt.encode(payload, "test-secret", algorithm="HS256")
        
        # Should work with require_store=False
        info = auth.verify_token(token, require_store=False)
        assert info.group == "admin"


# ============================================================================
# Test token revocation
# ============================================================================


class TestTokenRevocation:
    """Tests for token revocation."""

    def test_revoke_token(self):
        """Test revoking a token."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        token = auth.create_token(group="admin")
        assert token in auth.token_store
        
        result = auth.revoke_token(token)
        
        assert result is True
        assert token not in auth.token_store

    def test_revoke_nonexistent_token(self):
        """Test revoking a token that doesn't exist."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        result = auth.revoke_token("nonexistent-token")
        
        assert result is False


# ============================================================================
# Test token listing
# ============================================================================


class TestTokenListing:
    """Tests for listing tokens."""

    def test_list_tokens(self):
        """Test listing all tokens."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        token1 = auth.create_token(group="admin")
        token2 = auth.create_token(group="user")
        
        tokens = auth.list_tokens()
        
        assert len(tokens) == 2
        assert token1 in tokens
        assert token2 in tokens

    def test_list_tokens_empty(self):
        """Test listing tokens when store is empty."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        tokens = auth.list_tokens()
        
        assert tokens == {}


# ============================================================================
# Test get_group_for_token
# ============================================================================


class TestGetGroupForToken:
    """Tests for get_group_for_token."""

    def test_get_group_for_token(self):
        """Test getting group for a valid token."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        token = auth.create_token(group="admin")
        group = auth.get_group_for_token(token)
        
        assert group == "admin"

    def test_get_group_for_invalid_token(self):
        """Test getting group for an invalid token."""
        auth = AuthService(
            secret_key="test-secret",
            token_store_path=":memory:",
        )
        
        with pytest.raises(ValueError):
            auth.get_group_for_token("invalid-token")
