"""JWT Authentication Service.

Handles JWT token creation, validation, and group mapping.
Parameterized to work with any GOFR project via env_prefix.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

import jwt

from gofr_common.logger import Logger, create_logger


class SecurityAuditorProtocol(Protocol):
    """Protocol for security auditor integration.

    Projects can implement this protocol to receive security events
    from the auth service.
    """

    def log_auth_failure(
        self, client_id: str, reason: str, endpoint: Optional[str] = None, **details: Any
    ) -> None:
        """Log authentication failure."""
        ...


@dataclass
class TokenInfo:
    """Information extracted from a JWT token."""

    token: str
    group: str
    expires_at: datetime
    issued_at: datetime


class AuthService:
    """Service for JWT authentication and group management.

    Features:
    - JWT token creation with configurable expiry
    - Token verification with group extraction
    - Token revocation
    - File-based or in-memory token storage
    - Optional device fingerprinting for token binding
    - Enhanced JWT claims (nbf, aud, jti)

    Example:
        # Basic usage
        auth = AuthService(secret_key="my-secret", token_store_path="/path/to/tokens.json")
        token = auth.create_token(group="admin")
        info = auth.verify_token(token)

        # With environment variable fallback
        auth = AuthService(env_prefix="GOFR_DIG")  # Uses GOFR_DIG_JWT_SECRET

        # In-memory mode (for testing)
        auth = AuthService(secret_key="test", token_store_path=":memory:")
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        token_store_path: Optional[str] = None,
        env_prefix: str = "GOFR",
        logger: Optional[Logger] = None,
        audience: Optional[str] = None,
    ):
        """Initialize the authentication service.

        Args:
            secret_key: Secret key for JWT signing. Falls back to {env_prefix}_JWT_SECRET
            token_store_path: Path to store token-group mappings.
                             If None, uses {env_prefix}_TOKEN_STORE or default.
                             If ":memory:", uses in-memory storage without file persistence.
            env_prefix: Prefix for environment variables (e.g., "GOFR_DIG")
            logger: Optional logger instance. Creates one if not provided.
            audience: Optional JWT audience claim for token validation.
        """
        self.env_prefix = env_prefix.upper().replace("-", "_")
        self.audience = audience or f"{self.env_prefix.lower()}-api"

        # Setup logger - derive name from env_prefix (e.g., "GOFR_DIG" -> "gofr-dig-auth")
        if logger is not None:
            self.logger = logger
        else:
            # Convert prefix to logger name format
            logger_name = self.env_prefix.lower().replace("_", "-") + "-auth"
            self.logger = create_logger(name=logger_name)

        # Get or create secret key
        env_var = f"{self.env_prefix}_JWT_SECRET"
        secret = secret_key or os.environ.get(env_var)
        if not secret:
            self.logger.warning(
                "No JWT secret provided, generating random secret (not suitable for production)",
                hint=f"Set {env_var} environment variable for persistent tokens",
            )
            secret = os.urandom(32).hex()
        self.secret_key: str = secret

        # Setup token store
        if token_store_path is None:
            token_store_env = f"{self.env_prefix}_TOKEN_STORE"
            token_store_path = os.environ.get(token_store_env)

        # Check for in-memory mode
        self._use_memory_store = token_store_path == ":memory:"

        if self._use_memory_store:
            self.token_store_path: Optional[Path] = None
            self.token_store: Dict[str, Dict[str, Any]] = {}
            self.logger.info(
                "AuthService initialized with in-memory token store",
                secret_fingerprint=self._secret_fingerprint(),
            )
        else:
            if token_store_path:
                self.token_store_path = Path(token_store_path)
            else:
                # Default path - caller should typically provide this
                self.token_store_path = Path("data/auth/tokens.json")
            self._load_token_store()
            self.logger.info(
                "AuthService initialized",
                token_store=str(self.token_store_path),
                secret_fingerprint=self._secret_fingerprint(),
            )

    def _secret_fingerprint(self) -> str:
        """Return a stable fingerprint for the current secret without exposing it."""
        digest = hashlib.sha256(self.secret_key.encode()).hexdigest()
        return f"sha256:{digest[:12]}"

    def get_secret_fingerprint(self) -> str:
        """Public accessor for the JWT secret fingerprint."""
        return self._secret_fingerprint()

    def _load_token_store(self) -> None:
        """Load token-group mappings from disk (no-op for in-memory mode)."""
        if self._use_memory_store:
            self.logger.debug("In-memory mode: skipping token store load")
            return

        assert self.token_store_path is not None

        if self.token_store_path.exists():
            try:
                with open(self.token_store_path, "r") as f:
                    self.token_store = json.load(f)
                self.logger.debug(
                    "Token store loaded from disk",
                    tokens_count=len(self.token_store),
                    path=str(self.token_store_path),
                )
            except Exception as e:
                self.logger.error("Failed to load token store", error=str(e))
                self.token_store = {}
        else:
            self.token_store = {}
            self.logger.debug("Token store initialized as empty", path=str(self.token_store_path))

    def _save_token_store(self) -> None:
        """Save token-group mappings to disk (no-op for in-memory mode)."""
        if self._use_memory_store:
            self.logger.debug(
                "In-memory mode: skipping token store save",
                tokens_count=len(self.token_store),
            )
            return

        assert self.token_store_path is not None

        try:
            self.token_store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_store_path, "w") as f:
                json.dump(self.token_store, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            self.logger.debug("Token store saved", tokens_count=len(self.token_store))
        except Exception as e:
            self.logger.error("Failed to save token store", error=str(e))
            raise

    def create_token(
        self,
        group: str,
        expires_in_seconds: int = 2592000,
        fingerprint: Optional[str] = None,
        token_id: Optional[str] = None,
    ) -> str:
        """Create a new JWT token for a group.

        Args:
            group: The group name to associate with this token
            expires_in_seconds: Seconds until token expires (default: 30 days)
            fingerprint: Optional device/client fingerprint for binding
            token_id: Optional unique token identifier (jti) for revocation tracking

        Returns:
            JWT token string
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=expires_in_seconds)
        not_before = now

        payload: Dict[str, Any] = {
            "group": group,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "nbf": int(not_before.timestamp()),
            "aud": self.audience,
        }

        # Add optional claims for enhanced security
        if token_id:
            payload["jti"] = token_id
        if fingerprint:
            payload["fp"] = fingerprint

        token = jwt.encode(payload, self.secret_key, algorithm="HS256")

        # Store token-group mapping with metadata
        token_metadata: Dict[str, Any] = {
            "group": group,
            "issued_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "not_before": not_before.isoformat(),
        }
        if token_id:
            token_metadata["jti"] = token_id
        if fingerprint:
            token_metadata["fingerprint"] = fingerprint

        self.token_store[token] = token_metadata
        self._save_token_store()

        self.logger.info(
            "Token created",
            group=group,
            expires_at=expires_at.isoformat(),
            expires_in_seconds=expires_in_seconds,
        )

        return token

    def verify_token(
        self,
        token: str,
        fingerprint: Optional[str] = None,
        require_store: bool = True,
    ) -> TokenInfo:
        """Verify a JWT token and extract information.

        Args:
            token: JWT token string
            fingerprint: Optional device/client fingerprint to verify against token binding
            require_store: If True, token must exist in store (default). Set False for
                          stateless verification.

        Returns:
            TokenInfo with group and expiry information

        Raises:
            ValueError: If token is invalid, expired, or security checks fail
        """
        try:
            # Reload token store to get latest tokens created by admin
            self._load_token_store()

            # Decode and verify token with enhanced options
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"],
                options={
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": False,  # Don't require audience (backward compat)
                },
            )

            # Validate required claims
            group = payload.get("group")
            if not group:
                self.logger.error("Token missing group claim")
                raise ValueError("Token missing group claim")

            # Validate audience if present (optional for backward compatibility)
            if "aud" in payload and payload["aud"] != self.audience:
                self.logger.error("Token audience mismatch", aud=payload["aud"])
                raise ValueError("Token audience mismatch")

            # Validate fingerprint if token has one and fingerprint provided
            if "fp" in payload:
                stored_fp = payload["fp"]
                if fingerprint and stored_fp != fingerprint:
                    self.logger.warning(
                        "Token fingerprint mismatch",
                        group=group,
                        expected=stored_fp[:12] if stored_fp else None,
                        actual=fingerprint[:12] if fingerprint else None,
                    )
                    raise ValueError("Token fingerprint mismatch - possible token theft")

            # Check if token is in our store (if required)
            if require_store and token not in self.token_store:
                self.logger.warning("Token not found in store", group=group)
                raise ValueError("Token not found in token store. Tokens must be created by admin.")

            # Verify token metadata matches if in store
            if token in self.token_store:
                stored_metadata = self.token_store[token]
                if stored_metadata["group"] != group:
                    self.logger.error(
                        "Token group mismatch",
                        stored_group=stored_metadata["group"],
                        token_group=group,
                    )
                    raise ValueError("Token group mismatch in store")

            issued_at = datetime.fromtimestamp(payload["iat"])
            expires_at = datetime.fromtimestamp(payload["exp"])

            self.logger.debug("Token verified", group=group, expires_at=expires_at.isoformat())

            return TokenInfo(
                token=token,
                group=group,
                expires_at=expires_at,
                issued_at=issued_at,
            )

        except jwt.ExpiredSignatureError:
            self.logger.warning("Token expired")
            raise ValueError("Token has expired")
        except jwt.ImmatureSignatureError:
            self.logger.warning("Token not yet valid (nbf)")
            raise ValueError("Token not yet valid")
        except jwt.InvalidTokenError as e:
            self.logger.error("Invalid token", error=str(e))
            raise ValueError(f"Invalid token: {str(e)}")

    def revoke_token(self, token: str) -> bool:
        """Revoke a token by removing it from the store.

        Args:
            token: JWT token string to revoke

        Returns:
            True if token was found and revoked, False if not found
        """
        self._load_token_store()

        if token in self.token_store:
            group = self.token_store[token]["group"]
            del self.token_store[token]
            self._save_token_store()
            self.logger.info("Token revoked", group=group)
            return True
        else:
            self.logger.warning("Token not found for revocation")
            return False

    def list_tokens(self) -> Dict[str, Dict[str, Any]]:
        """List all tokens in the store.

        Returns:
            Dictionary of token -> token info
        """
        self._load_token_store()
        return self.token_store.copy()

    def get_group_for_token(self, token: str) -> str:
        """Get the group associated with a token.

        Args:
            token: JWT token string

        Returns:
            Group name

        Raises:
            ValueError: If token is invalid
        """
        token_info = self.verify_token(token)
        return token_info.group
