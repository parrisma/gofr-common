"""Factory functions for creating storage backends.

Provides convenient factory functions to create token and group stores
based on configuration or environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional, Tuple, Union

from gofr_common.logger import Logger, create_logger

from .base import GroupStore, TokenStore
from .file import FileGroupStore, FileTokenStore
from .memory import MemoryGroupStore, MemoryTokenStore
from ..identity import VaultIdentity, VaultIdentityError

if TYPE_CHECKING:
    from .vault_client import VaultClient


BackendType = Literal["memory", "file", "vault"]


class FactoryError(Exception):
    """Raised when factory fails to create a store."""
    pass


def create_token_store(
    backend: BackendType,
    *,
    # File backend options
    path: Optional[Union[str, Path]] = None,
    # Vault backend options
    vault_client: Optional["VaultClient"] = None,
    vault_path_prefix: str = "gofr/auth",
    # Common options
    logger: Optional[Logger] = None,
) -> TokenStore:
    """Create a token store based on backend type.

    Args:
        backend: Type of backend - "memory", "file", or "vault"
        path: Path for file backend (required for "file")
        vault_client: VaultClient for vault backend (required for "vault")
        vault_path_prefix: Path prefix in Vault for secrets
        logger: Optional logger instance

    Returns:
        TokenStore implementation

    Raises:
        FactoryError: If required options are missing

    Example:
        # Memory store (for testing)
        store = create_token_store("memory")

        # File store
        store = create_token_store("file", path="/data/auth/tokens.json")

        # Vault store
        client = VaultClient(config)
        store = create_token_store("vault", vault_client=client)
    """
    if backend == "memory":
        # Memory stores don't use logger
        return MemoryTokenStore()

    elif backend == "file":
        if path is None:
            raise FactoryError("'path' is required for file backend")
        return FileTokenStore(path=path, logger=logger)

    elif backend == "vault":
        if vault_client is None:
            raise FactoryError("'vault_client' is required for vault backend")
        # Late import to avoid circular dependency
        from .vault import VaultTokenStore
        return VaultTokenStore(
            client=vault_client,
            path_prefix=vault_path_prefix,
            logger=logger,
        )

    else:
        raise FactoryError(f"Unknown backend type: {backend}")


def create_group_store(
    backend: BackendType,
    *,
    # File backend options
    path: Optional[Union[str, Path]] = None,
    # Vault backend options
    vault_client: Optional["VaultClient"] = None,
    vault_path_prefix: str = "gofr/auth",
    # Common options
    logger: Optional[Logger] = None,
) -> GroupStore:
    """Create a group store based on backend type.

    Args:
        backend: Type of backend - "memory", "file", or "vault"
        path: Path for file backend (required for "file")
        vault_client: VaultClient for vault backend (required for "vault")
        vault_path_prefix: Path prefix in Vault for secrets
        logger: Optional logger instance

    Returns:
        GroupStore implementation

    Raises:
        FactoryError: If required options are missing

    Example:
        # Memory store (for testing)
        store = create_group_store("memory")

        # File store
        store = create_group_store("file", path="/data/auth/groups.json")

        # Vault store
        client = VaultClient(config)
        store = create_group_store("vault", vault_client=client)
    """
    if backend == "memory":
        # Memory stores don't use logger
        return MemoryGroupStore()

    elif backend == "file":
        if path is None:
            raise FactoryError("'path' is required for file backend")
        return FileGroupStore(path=path, logger=logger)

    elif backend == "vault":
        if vault_client is None:
            raise FactoryError("'vault_client' is required for vault backend")
        # Late import to avoid circular dependency
        from .vault import VaultGroupStore
        return VaultGroupStore(
            client=vault_client,
            path_prefix=vault_path_prefix,
            logger=logger,
        )

    else:
        raise FactoryError(f"Unknown backend type: {backend}")


def create_stores_from_env(
    prefix: str = "GOFR",
    *,
    logger: Optional[Logger] = None,
) -> Tuple[TokenStore, GroupStore]:
    """Create token and group stores from environment variables.

    Reads configuration from environment:
    - {PREFIX}_AUTH_BACKEND: Backend type ("memory", "file", "vault")
    - For file backend:
      - {PREFIX}_DATA_DIR: Base data directory
    - For vault backend:
      - {PREFIX}_VAULT_URL: Vault server URL
      - {PREFIX}_VAULT_TOKEN: Vault token (or use AppRole)
      - {PREFIX}_VAULT_ROLE_ID: AppRole role ID
      - {PREFIX}_VAULT_SECRET_ID: AppRole secret ID
      - {PREFIX}_VAULT_MOUNT_POINT: KV mount point (default: "secret")
      - {PREFIX}_VAULT_PATH_PREFIX: Path prefix (default: "{prefix}/auth")

    Args:
        prefix: Environment variable prefix (e.g., "GOFR_DIG")
        logger: Optional logger instance

    Returns:
        Tuple of (TokenStore, GroupStore)

    Raises:
        FactoryError: If configuration is invalid or missing

    Example:
        # With GOFR_DIG_AUTH_BACKEND=vault and vault env vars set
        token_store, group_store = create_stores_from_env("GOFR_DIG")
    """
    log = logger or create_logger(name="store-factory")

    # Normalize prefix (strip trailing underscore if present)
    prefix = prefix.rstrip("_")

    # Read backend type
    backend_str = os.environ.get(f"{prefix}_AUTH_BACKEND", "memory").lower()

    if backend_str not in ("memory", "file", "vault"):
        raise FactoryError(
            f"Invalid backend type '{backend_str}'. "
            f"Must be 'memory', 'file', or 'vault'"
        )

    backend: BackendType = backend_str  # type: ignore

    log.debug(f"Creating stores with backend: {backend}", prefix=prefix)

    if backend == "memory":
        # Memory stores don't use logger
        return (
            MemoryTokenStore(),
            MemoryGroupStore(),
        )

    elif backend == "file":
        # Get data directory
        data_dir = os.environ.get(f"{prefix}_DATA_DIR")
        if not data_dir:
            raise FactoryError(
                f"{prefix}_DATA_DIR is required for file backend"
            )

        auth_dir = Path(data_dir) / "auth"
        tokens_path = auth_dir / "tokens.json"
        groups_path = auth_dir / "groups.json"

        log.debug(
            "Using file backend",
            tokens_path=str(tokens_path),
            groups_path=str(groups_path),
        )

        return (
            FileTokenStore(path=tokens_path, logger=logger),
            FileGroupStore(path=groups_path, logger=logger),
        )

    else:  # vault
        # Late imports for vault
        from .vault import VaultGroupStore, VaultTokenStore
        from .vault_client import VaultClient
        from .vault_config import VaultConfig

        # Prefer AppRole credentials injected at /run/secrets/vault_creds
        # to avoid relying on potentially stale/placeholder GOFR_VAULT_TOKEN
        vault_client: VaultClient
        env_prefix = prefix.upper().replace("-", "_")
        if VaultIdentity.is_available():
            try:
                identity = VaultIdentity(
                    vault_addr=os.environ.get(f"{env_prefix}_VAULT_URL"),
                ).login()
                vault_client = identity.get_client()
            except VaultIdentityError as e:
                raise FactoryError(f"Vault identity login failed: {e}") from e
        else:
            # Fall back to env-based config (token or AppRole via env vars)
            vault_config = VaultConfig.from_env(prefix)
            vault_client = VaultClient(vault_config, logger=logger)

        # Get path prefix (default to lowercase prefix)
        default_prefix = f"{prefix.lower().replace('_', '/')}/auth"
        path_prefix = os.environ.get(
            f"{prefix}_VAULT_PATH_PREFIX",
            default_prefix,
        )

        log.debug(
            "Using vault backend",
            path_prefix=path_prefix,
        )

        return (
            VaultTokenStore(
                client=vault_client,
                path_prefix=path_prefix,
                logger=logger,
            ),
            VaultGroupStore(
                client=vault_client,
                path_prefix=path_prefix,
                logger=logger,
            ),
        )
