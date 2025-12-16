"""JWT Authentication Service.

Handles JWT token creation, validation, and group mapping.
Parameterized to work with any GOFR project via env_prefix.
Now supports multi-group tokens with a central group registry.
Supports pluggable storage backends via TokenStore protocol.
"""

import hashlib
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional, Protocol

import jwt

from gofr_common.logger import Logger, create_logger

from .backends import TokenStore
from .groups import Group, GroupRegistry
from .tokens import TokenInfo, TokenRecord


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


class InvalidGroupError(Exception):
    """Raised when token references an invalid or defunct group."""

    pass


class TokenNotFoundError(Exception):
    """Raised when a token is not found in the store."""

    pass


class TokenRevokedError(Exception):
    """Raised when a token has been revoked."""

    pass


class AuthService:
    """Service for JWT authentication and multi-group management.

    Features:
    - JWT token creation with configurable expiry
    - Multi-group tokens with group validation
    - Token verification with group extraction
    - Soft-delete token revocation (tokens never deleted)
    - Central group registry with reserved groups
    - Pluggable storage backends (memory, file, vault)
    - Optional device fingerprinting for token binding
    - Enhanced JWT claims (nbf, aud, jti)

    Example:
        from gofr_common.auth.backends import MemoryTokenStore, MemoryGroupStore

        # Create stores
        token_store = MemoryTokenStore()
        group_store = MemoryGroupStore()
        group_registry = GroupRegistry(store=group_store)

        # Create service
        auth = AuthService(
            secret_key="my-secret",
            token_store=token_store,
            group_registry=group_registry,
        )
        token = auth.create_token(groups=["admin", "users"])
        info = auth.verify_token(token)
        print(info.groups)  # ["admin", "users"]

        # With environment variable fallback for secret
        auth = AuthService(
            token_store=token_store,
            group_registry=group_registry,
            env_prefix="GOFR_DIG",  # Uses GOFR_DIG_JWT_SECRET
        )
    """

    def __init__(
        self,
        token_store: TokenStore,
        group_registry: GroupRegistry,
        secret_key: Optional[str] = None,
        env_prefix: str = "GOFR",
        logger: Optional[Logger] = None,
        audience: Optional[str] = None,
    ):
        """Initialize the authentication service.

        Args:
            token_store: TokenStore instance for token storage (memory, file, vault)
            group_registry: GroupRegistry instance for group management
            secret_key: Secret key for JWT signing. Falls back to {env_prefix}_JWT_SECRET
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

        # Store references
        self._token_store = token_store
        self._group_registry = group_registry

        self.logger.info(
            "AuthService initialized",
            token_store_type=type(token_store).__name__,
            group_store_type=type(group_registry._store).__name__,
            secret_fingerprint=self._secret_fingerprint(),
        )

    @property
    def groups(self) -> GroupRegistry:
        """Access the group registry.

        Returns:
            The GroupRegistry instance for this AuthService
        """
        return self._group_registry

    def _secret_fingerprint(self) -> str:
        """Return a stable fingerprint for the current secret without exposing it."""
        digest = hashlib.sha256(self.secret_key.encode()).hexdigest()
        return f"sha256:{digest[:12]}"

    def get_secret_fingerprint(self) -> str:
        """Public accessor for the JWT secret fingerprint."""
        return self._secret_fingerprint()

    def _reload_store(self) -> None:
        """Reload token store from backend (for file/vault backends)."""
        self._token_store.reload()

    def create_token(
        self,
        groups: List[str],
        expires_in_seconds: int = 2592000,
        fingerprint: Optional[str] = None,
    ) -> str:
        """Create a new JWT token for one or more groups.

        Args:
            groups: List of group names to associate with this token.
                   All groups must exist and be active in the registry.
            expires_in_seconds: Seconds until token expires (default: 30 days)
            fingerprint: Optional device/client fingerprint for binding

        Returns:
            JWT token string

        Raises:
            InvalidGroupError: If any group doesn't exist or is defunct
        """
        # Validate all groups exist and are active
        for group_name in groups:
            group = self._group_registry.get_group_by_name(group_name)
            if group is None:
                raise InvalidGroupError(f"Group '{group_name}' does not exist")
            if not group.is_active:
                raise InvalidGroupError(f"Group '{group_name}' is defunct")

        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=expires_in_seconds)
        not_before = now

        # Create token record
        token_record = TokenRecord.create(
            groups=groups,
            expires_at=expires_at,
            fingerprint=fingerprint,
        )

        # Build JWT payload with UUID reference
        payload: Dict[str, Any] = {
            "jti": str(token_record.id),  # Token ID is the UUID
            "groups": groups,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "nbf": int(not_before.timestamp()),
            "aud": self.audience,
        }

        if fingerprint:
            payload["fp"] = fingerprint

        jwt_token = jwt.encode(payload, self.secret_key, algorithm="HS256")

        # Store token record keyed by UUID
        self._token_store.put(str(token_record.id), token_record)

        self.logger.info(
            "Token created",
            token_id=str(token_record.id),
            groups=groups,
            expires_at=expires_at.isoformat(),
            expires_in_seconds=expires_in_seconds,
        )

        return jwt_token

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
            TokenInfo with groups and expiry information

        Raises:
            ValueError: If token is invalid, expired, revoked, or security checks fail
        """
        try:
            # Reload token store to get latest tokens
            self._reload_store()

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

            # Extract token ID (UUID)
            token_id = payload.get("jti")
            if not token_id:
                self.logger.error("Token missing jti claim")
                raise ValueError("Token missing jti claim")

            # Get groups from payload
            groups = payload.get("groups")
            if not groups:
                self.logger.error("Token missing groups claim")
                raise ValueError("Token missing groups claim")

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
                        token_id=token_id,
                        expected=stored_fp[:12] if stored_fp else None,
                        actual=fingerprint[:12] if fingerprint else None,
                    )
                    raise ValueError("Token fingerprint mismatch - possible token theft")

            # Check if token is in our store (if required)
            if require_store:
                if not self._token_store.exists(token_id):
                    self.logger.warning("Token not found in store", token_id=token_id)
                    raise TokenNotFoundError(f"Token {token_id} not found in token store")

                token_record = self._token_store.get(token_id)
                if token_record is None:
                    self.logger.warning("Token not found in store", token_id=token_id)
                    raise TokenNotFoundError(f"Token {token_id} not found in token store")

                # Check if token is revoked
                if token_record.status == "revoked":
                    self.logger.warning("Token has been revoked", token_id=token_id)
                    raise TokenRevokedError(f"Token {token_id} has been revoked")

                # Verify groups match store
                if set(token_record.groups) != set(groups):
                    self.logger.error(
                        "Token groups mismatch",
                        stored_groups=token_record.groups,
                        token_groups=groups,
                    )
                    raise ValueError("Token groups mismatch in store")

            issued_at = datetime.fromtimestamp(payload["iat"])
            expires_at = datetime.fromtimestamp(payload["exp"])

            self.logger.debug(
                "Token verified",
                token_id=token_id,
                groups=groups,
                expires_at=expires_at.isoformat(),
            )

            return TokenInfo(
                token=token,
                groups=groups,
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
        """Revoke a token by setting its status to "revoked".

        Tokens are soft-deleted - they remain in the store but are
        marked as revoked with a timestamp.

        Args:
            token: JWT token string to revoke

        Returns:
            True if token was found and revoked, False if not found
        """
        self._reload_store()

        try:
            # Decode token to get UUID (don't verify expiry for revocation)
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"],
                options={
                    "verify_exp": False,
                    "verify_nbf": False,
                    "verify_iat": True,
                    "verify_aud": False,
                },
            )
            token_id = payload.get("jti")
            if not token_id:
                self.logger.warning("Token missing jti claim for revocation")
                return False
        except jwt.InvalidTokenError as e:
            self.logger.warning("Invalid token for revocation", error=str(e))
            return False

        if self._token_store.exists(token_id):
            token_record = self._token_store.get(token_id)
            if token_record is None:
                self.logger.warning("Token not found for revocation", token_id=token_id)
                return False

            # Check if already revoked
            if token_record.status == "revoked":
                self.logger.info("Token already revoked", token_id=token_id)
                return True

            # Soft-delete: set status and timestamp
            token_record.status = "revoked"
            token_record.revoked_at = datetime.utcnow()

            # Update in store
            self._token_store.put(token_id, token_record)
            self.logger.info("Token revoked", token_id=token_id, groups=token_record.groups)
            return True
        else:
            self.logger.warning("Token not found for revocation", token_id=token_id)
            return False

    def list_tokens(
        self,
        status: Optional[Literal["active", "revoked"]] = None,
    ) -> List[TokenRecord]:
        """List all tokens in the store.

        Args:
            status: Optional filter by status ("active" or "revoked").
                   If None, returns all tokens.

        Returns:
            List of TokenRecord objects
        """
        self._reload_store()

        records = list(self._token_store.list_all().values())

        if status is not None:
            records = [r for r in records if r.status == status]

        return records

    def get_token_by_id(self, token_id: str) -> Optional[TokenRecord]:
        """Get a token record by its UUID.

        Args:
            token_id: UUID string of the token

        Returns:
            TokenRecord if found, None otherwise
        """
        self._reload_store()
        if self._token_store.exists(token_id):
            return self._token_store.get(token_id)
        return None

    def resolve_token_groups(
        self,
        token: str,
        include_defunct: bool = False,
    ) -> List[Group]:
        """Resolve a token to its list of Group objects.

        The `public` group is always included in the result, even if
        not explicitly in the token.

        Args:
            token: JWT token string
            include_defunct: If True, include defunct groups (default False)

        Returns:
            List of Group objects the token grants access to

        Raises:
            ValueError: If token is invalid
        """
        token_info = self.verify_token(token)

        resolved_groups: List[Group] = []
        seen_names: set = set()

        # Get all groups from token
        for group_name in token_info.groups:
            if group_name in seen_names:
                continue
            group = self._group_registry.get_group_by_name(group_name)
            if group is not None:
                if include_defunct or group.is_active:
                    resolved_groups.append(group)
                    seen_names.add(group_name)

        # Always include public group
        if "public" not in seen_names:
            public_group = self._group_registry.get_group_by_name("public")
            if public_group is not None:
                resolved_groups.append(public_group)

        return resolved_groups
