"""Storage backends for GOFR authentication.

Provides pluggable storage backends for tokens and groups:
- MemoryTokenStore / MemoryGroupStore - In-memory storage for testing
- FileTokenStore / FileGroupStore - File-based JSON storage
- VaultTokenStore / VaultGroupStore - HashiCorp Vault storage (requires hvac)

Usage:
    from gofr_common.auth.backends import (
        TokenStore,
        GroupStore,
        MemoryTokenStore,
        MemoryGroupStore,
        FileTokenStore,
        FileGroupStore,
        VaultConfig,
        VaultClient,
        create_token_store,
        create_group_store,
        create_stores_from_env,
    )

    # Create in-memory stores for testing
    token_store = MemoryTokenStore()
    group_store = MemoryGroupStore()

    # Create file-based stores for production
    token_store = FileTokenStore(Path("/data/auth/tokens.json"))
    group_store = FileGroupStore(Path("/data/auth/groups.json"))

    # Configure Vault connection
    vault_config = VaultConfig.from_env("GOFR_DIG")
    vault_client = VaultClient(vault_config)

    # Or use factory functions
    token_store, group_store = create_stores_from_env("GOFR_DIG")
"""

from .base import GroupStore, StorageError, StorageUnavailableError, TokenStore
from .factory import (
    BackendType,
    FactoryError,
    create_group_store,
    create_stores_from_env,
    create_token_store,
)
from .file import FileGroupStore, FileTokenStore
from .memory import MemoryGroupStore, MemoryTokenStore
from .vault import VaultGroupStore, VaultTokenStore
from .vault_client import (
    VaultAuthenticationError,
    VaultClient,
    VaultConnectionError,
    VaultError,
    VaultNotFoundError,
    VaultPermissionError,
)
from .vault_config import VaultConfig, VaultConfigError

__all__ = [
    # Protocols
    "TokenStore",
    "GroupStore",
    # Exceptions - Storage
    "StorageError",
    "StorageUnavailableError",
    # Exceptions - Vault Config
    "VaultConfigError",
    # Exceptions - Vault Client
    "VaultError",
    "VaultConnectionError",
    "VaultAuthenticationError",
    "VaultNotFoundError",
    "VaultPermissionError",
    # Exceptions - Factory
    "FactoryError",
    # Memory backends
    "MemoryTokenStore",
    "MemoryGroupStore",
    # File backends
    "FileTokenStore",
    "FileGroupStore",
    # Vault
    "VaultConfig",
    "VaultClient",
    "VaultTokenStore",
    "VaultGroupStore",
    # Factory functions
    "create_token_store",
    "create_group_store",
    "create_stores_from_env",
    "BackendType",
]
