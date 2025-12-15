"""Authentication module for GOFR projects.

Provides JWT-based authentication with:
- Token creation, verification, and revocation
- Multi-group access control with reserved groups (public, admin)
- Central group registry with soft-delete (defunct) support
- Authorization helpers for FastAPI endpoints
- Optional token fingerprinting for theft detection
- In-memory or file-based token storage
- FastAPI middleware integration

Usage:
    from gofr_common.auth import AuthService, TokenInfo, init_auth_service
    from gofr_common.auth import Group, GroupRegistry, RESERVED_GROUPS
    from gofr_common.auth import TokenRecord
    from gofr_common.auth import require_admin, require_group, require_any_group
    
    # Create auth service
    auth_service = AuthService(
        secret_key="your-secret",
        token_store_path="/path/to/tokens.json",
        env_prefix="GOFR_DIG",  # For env var fallback
    )
    
    # Create a token
    token = auth_service.create_token(groups=["admin"], expires_in_seconds=86400)
    
    # Verify a token
    token_info = auth_service.verify_token(token)
    print(token_info.groups)  # ["admin"]
    
    # Group registry (auto-bootstraps reserved groups)
    registry = GroupRegistry(store_path="/path/to/groups.json")
    users_group = registry.create_group("users", "Regular users")
    
    # FastAPI endpoint with admin requirement
    @app.post("/groups")
    def create_group(token: TokenInfo = Depends(require_admin)):
        ...
"""

from .service import AuthService, InvalidGroupError, TokenNotFoundError, TokenRevokedError
from .tokens import TokenInfo, TokenRecord
from .groups import (
    Group,
    GroupRegistry,
    GroupRegistryError,
    ReservedGroupError,
    DuplicateGroupError,
    GroupNotFoundError,
    RESERVED_GROUPS,
)
from .middleware import (
    get_auth_service,
    verify_token,
    verify_token_simple,
    init_auth_service,
    optional_verify_token,
    set_security_auditor,
    get_security_auditor,
    require_group,
    require_any_group,
    require_all_groups,
    require_admin,
)

__all__ = [
    # Service
    "AuthService",
    "InvalidGroupError",
    "TokenNotFoundError",
    "TokenRevokedError",
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
    # Middleware
    "get_auth_service",
    "verify_token",
    "verify_token_simple",
    "optional_verify_token",
    "init_auth_service",
    "set_security_auditor",
    "get_security_auditor",
    # Authorization helpers
    "require_group",
    "require_any_group",
    "require_all_groups",
    "require_admin",
]

