"""GOFR Common - Shared infrastructure for GOFR projects.

This package provides common functionality shared across all GOFR projects:
- logger: Flexible logging with session tracking and JSON support
- testing: Code quality testing utilities (ruff, pyright integration)
- auth: Authentication services and middleware (coming soon)
- config: Configuration management (coming soon)
- exceptions: Common exception classes (coming soon)
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
]
