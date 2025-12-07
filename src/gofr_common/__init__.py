"""GOFR Common - Shared infrastructure for GOFR projects.

This package provides common functionality shared across all GOFR projects:
- logger: Flexible logging with session tracking and JSON support
- testing: Code quality testing utilities (ruff, pyright integration)
- auth: JWT authentication services and FastAPI middleware
- config: Configuration management with typed settings
- exceptions: Common exception classes with structured error info
"""

__version__ = "1.0.0"

# Re-export commonly used items for convenience
from gofr_common.logger import (
    Logger,
    DefaultLogger,
    ConsoleLogger,
    StructuredLogger,
    get_logger,
    create_logger,
)

from gofr_common.testing import (
    CheckResult,
    CodeQualityChecker,
)

from gofr_common.auth import (
    AuthService,
    TokenInfo,
    init_auth_service,
    get_auth_service,
    verify_token,
    optional_verify_token,
)

from gofr_common.config import (
    Config,
    Settings,
    ServerSettings,
    AuthSettings,
    StorageSettings,
    LogSettings,
    get_settings,
    reset_settings,
)

from gofr_common.exceptions import (
    GofrError,
    ValidationError,
    ResourceNotFoundError,
    SecurityError,
    ConfigurationError,
    RegistryError,
)

__all__ = [
    "__version__",
    # Logger
    "Logger",
    "DefaultLogger",
    "ConsoleLogger",
    "StructuredLogger",
    "get_logger",
    "create_logger",
    # Testing
    "CheckResult",
    "CodeQualityChecker",
    # Auth
    "AuthService",
    "TokenInfo",
    "init_auth_service",
    "get_auth_service",
    "verify_token",
    "optional_verify_token",
    # Config
    "Config",
    "Settings",
    "ServerSettings",
    "AuthSettings",
    "StorageSettings",
    "LogSettings",
    "get_settings",
    "reset_settings",
    # Exceptions
    "GofrError",
    "ValidationError",
    "ResourceNotFoundError",
    "SecurityError",
    "ConfigurationError",
    "RegistryError",
]
