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

from gofr_common.config.base import (
    Config,
    get_default_proxy_dir,
    get_default_sessions_dir,
    get_default_storage_dir,
    get_default_token_store_path,
    get_public_storage_dir,
)
from gofr_common.config.ports import (
    GOFR_DIG_PORTS,
    GOFR_DOC_PORTS,
    GOFR_IQ_PORTS,
    GOFR_NP_PORTS,
    GOFR_PLOT_PORTS,
    PORTS,
    ServicePorts,
    get_ports,
    list_services,
    next_available_base,
    register_service,
)
from gofr_common.config.settings import (
    AuthSettings,
    LogSettings,
    ServerSettings,
    Settings,
    StorageSettings,
    get_settings,
    reset_settings,
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
    # Port configuration
    "ServicePorts",
    "PORTS",
    "get_ports",
    "register_service",
    "list_services",
    "next_available_base",
    "GOFR_DOC_PORTS",
    "GOFR_PLOT_PORTS",
    "GOFR_NP_PORTS",
    "GOFR_DIG_PORTS",
    "GOFR_IQ_PORTS",
    "get_public_storage_dir",
]
