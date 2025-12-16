"""Authentication module for GOFR projects.

Provides JWT-based authentication with:
- Token creation, verification, and revocation
- Multi-group access control with reserved groups (public, admin)
- Central group registry with soft-delete (defunct) support
- Authorization helpers for FastAPI endpoints
- Optional token fingerprinting for theft detection
- Pluggable storage backends (memory, file, vault)
- FastAPI middleware integration

Usage:
    from gofr_common.auth import AuthService, TokenInfo
    from gofr_common.auth import Group, GroupRegistry, RESERVED_GROUPS
    from gofr_common.auth import TokenRecord
    from gofr_common.auth import require_admin, require_group
    from gofr_common.auth import MemoryTokenStore, MemoryGroupStore

    # Create stores (memory for testing)
    token_store = MemoryTokenStore()
    group_store = MemoryGroupStore()
    group_registry = GroupRegistry(store=group_store)

    # Create auth service
    auth_service = AuthService(
        secret_key="your-secret",
        token_store=token_store,
        group_registry=group_registry,
        env_prefix="GOFR_DIG",  # For env var fallback
    )

    # Create a token
    token = auth_service.create_token(groups=["admin"], expires_in_seconds=86400)

    # Verify a token
    token_info = auth_service.verify_token(token)
    print(token_info.groups)  # ["admin"]

    # FastAPI endpoint with admin requirement
    @app.post("/groups")
    def create_group(token: TokenInfo = Depends(require_admin)):
        ...
"""

from .backends import (
    FactoryError,
    FileGroupStore,
    # File backends
    FileTokenStore,
    GroupStore,
    MemoryGroupStore,
    # Memory backends
    MemoryTokenStore,
    # Exceptions
    StorageError,
    StorageUnavailableError,
    # Protocols
    TokenStore,
    VaultAuthenticationError,
    VaultClient,
    # Vault backends
    VaultConfig,
    VaultConnectionError,
    VaultError,
    VaultGroupStore,
    VaultNotFoundError,
    VaultPermissionError,
    VaultTokenStore,
    create_group_store,
    create_stores_from_env,
    # Factory functions
    create_token_store,
)
from .exceptions import (
    AuthenticationError,
    AuthError,
    FingerprintMismatchError,
    GroupAccessDeniedError,
    GroupError,
    InvalidGroupError,
    TokenError,
    TokenExpiredError,
    TokenNotFoundError,
    TokenRevokedError,
    TokenServiceError,
    TokenValidationError,
)
from .groups import (
    RESERVED_GROUPS,
    DuplicateGroupError,
    Group,
    GroupNotFoundError,
    GroupRegistry,
    GroupRegistryError,
    ReservedGroupError,
)
from .middleware import (
    get_auth_service,
    get_security_auditor,
    init_auth_service,
    optional_verify_token,
    require_admin,
    require_all_groups,
    require_any_group,
    require_group,
    set_security_auditor,
    verify_token,
    verify_token_simple,
)
from .provider import AuthProvider, SecurityAuditorProtocol, create_auth_provider
from .service import AuthService
from .token_service import TokenService
from .tokens import TokenInfo, TokenRecord

__all__ = [
    # Service
    "AuthService",
    # Token Service (low-level JWT operations)
    "TokenService",
    # Provider (DI - recommended)
    "AuthProvider",
    "SecurityAuditorProtocol",
    "create_auth_provider",
    # Tokens
    "TokenInfo",
    "TokenRecord",
    # Groups
    "Group",
    "GroupRegistry",
    "GroupRegistryError",
    "ReservedGroupError",
    "DuplicateGroupError",
    "GroupNotFoundError",
    "RESERVED_GROUPS",
    # Exception Hierarchy
    "AuthError",
    "TokenError",
    "TokenNotFoundError",
    "TokenRevokedError",
    "TokenExpiredError",
    "TokenValidationError",
    "TokenServiceError",
    "GroupError",
    "InvalidGroupError",
    "GroupAccessDeniedError",
    "AuthenticationError",
    "FingerprintMismatchError",
    # Middleware (global state - backward compatible)
    "get_auth_service",
    "verify_token",
    "verify_token_simple",
    "optional_verify_token",
    "init_auth_service",
    "set_security_auditor",
    "get_security_auditor",
    # Authorization helpers (global state)
    "require_group",
    "require_any_group",
    "require_all_groups",
    "require_admin",
    # Storage Protocols
    "TokenStore",
    "GroupStore",
    # Memory backends
    "MemoryTokenStore",
    "MemoryGroupStore",
    # File backends
    "FileTokenStore",
    "FileGroupStore",
    # Vault backends
    "VaultConfig",
    "VaultClient",
    "VaultTokenStore",
    "VaultGroupStore",
    "VaultError",
    "VaultConnectionError",
    "VaultAuthenticationError",
    "VaultNotFoundError",
    "VaultPermissionError",
    # Factory functions
    "create_token_store",
    "create_group_store",
    "create_stores_from_env",
    # Storage exceptions
    "StorageError",
    "StorageUnavailableError",
    "FactoryError",
]
