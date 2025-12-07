"""Authentication module for GOFR projects.

Provides JWT-based authentication with:
- Token creation, verification, and revocation
- Group-based access control
- Optional token fingerprinting for theft detection
- In-memory or file-based token storage
- FastAPI middleware integration

Usage:
    from gofr_common.auth import AuthService, TokenInfo, init_auth_service
    
    # Create auth service
    auth_service = AuthService(
        secret_key="your-secret",
        token_store_path="/path/to/tokens.json",
        env_prefix="GOFR_DIG",  # For env var fallback
    )
    
    # Create a token
    token = auth_service.create_token(group="admin", expires_in_seconds=86400)
    
    # Verify a token
    token_info = auth_service.verify_token(token)
    print(token_info.group)  # "admin"
"""

from .service import AuthService, TokenInfo
from .middleware import (
    get_auth_service,
    verify_token,
    init_auth_service,
    optional_verify_token,
    set_security_auditor,
    get_security_auditor,
)

__all__ = [
    # Service
    "AuthService",
    "TokenInfo",
    # Middleware
    "get_auth_service",
    "verify_token",
    "optional_verify_token",
    "init_auth_service",
    "set_security_auditor",
    "get_security_auditor",
]
