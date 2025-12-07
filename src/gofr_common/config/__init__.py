"""Configuration Module for GOFR Applications

Provides unified, typed configuration management with environment variable support.
All settings classes accept a parameterized env_prefix for project-specific configuration.

Example:
    from gofr_common.config import Settings, Config

    # Full settings object
    settings = Settings.from_env(prefix="GOFR_DOC")

    # Legacy Config class
    data_dir = Config.get_data_dir()
"""

from gofr_common.config.settings import (
    ServerSettings,
    AuthSettings,
    StorageSettings,
    LogSettings,
    Settings,
    get_settings,
    reset_settings,
)
from gofr_common.config.base import (
    Config,
    get_default_storage_dir,
    get_default_token_store_path,
    get_default_sessions_dir,
    get_default_proxy_dir,
    get_public_storage_dir,
)

__all__ = [
    # Dataclass settings
    "ServerSettings",
    "AuthSettings",
    "StorageSettings",
    "LogSettings",
    "Settings",
    # Singleton
    "get_settings",
    "reset_settings",
    # Legacy Config class
    "Config",
    # Convenience functions
    "get_default_storage_dir",
    "get_default_token_store_path",
    "get_default_sessions_dir",
    "get_default_proxy_dir",
    "get_public_storage_dir",
]
