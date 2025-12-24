# gofr-common

Shared infrastructure library for GOFR projects.

## Overview

This package provides common functionality shared across all GOFR microservices:

- **gofr-dig** - Web scraping and content extraction
- **gofr-plot** - Graph rendering service
- **gofr-np** - Numerical/math operations
- **gofr-doc** - Document generation
- **gofr-iq** - Intelligence and query service

## Documentation

| Topic | Description |
|-------|-------------|
| [**Authentication**](docs/GOFR_AUTH_SYSTEM.md) | JWT-based auth system, group management, and Vault integration. |
| [**Backup System**](docs/BACKUP.md) | Automated backup infrastructure, retention policies, and verification. |
| [**Port Standards**](docs/PORT_STANDARDIZATION.md) | Standardized port allocation strategy for all services. |
| [**Dev Standards**](docs/GOFR_DEVELOPMENT_STANDARDS.md) | Coding style, testing requirements, and project structure. |
| [**VS Code**](docs/VSCODE_LAUNCH_STANDARDS.md) | Debugging configurations and launch profiles. |

## Components

| Module | Description |
|--------|-------------|
| `gofr_common.auth` | JWT authentication service and middleware |
| `gofr_common.backup` | Backup orchestration and housekeeping |
| `gofr_common.config` | Configuration management and port allocation |
| `gofr_common.logger` | Structured logging interface |
| `gofr_common.mcp` | MCP server utilities and response helpers |
| `gofr_common.web` | Common web middleware (CORS, health checks) |

## Installation

### As a dependency

```bash
# From local path (development)
uv pip install -e /path/to/gofr-common

# Or add to pyproject.toml
[tool.uv]
dev-dependencies = [
    "gofr-common @ file:../gofr-common",
]
```

### With optional dependencies

```bash
uv pip install -e ".[pdf,plotting,all]"
```

## Docker Base Image

Build the shared base image used by all GOFR projects:

```bash
cd docker
./build-base.sh
```

## Quick Usage

### Logging

```python
from gofr_common.logger import ConsoleLogger

logger = ConsoleLogger(name="my-service")
logger.info("Server started", port=8000, host="0.0.0.0")
```

### Configuration

```python
from gofr_common.config import Settings

# Load all settings from environment (with defaults)
settings = Settings.from_env(prefix="GOFR_DIG")

print(f"Data Dir: {settings.storage.data_dir}")
print(f"MCP Port: {settings.server.mcp_port}")
```

## Development

```bash
# Run all tests (includes Vault integration)
./scripts/run_tests.sh --vault

# Run specific test
./scripts/run_tests.sh tests/test_config.py
```

## License

MIT
