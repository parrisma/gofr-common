# gofr-common

Shared infrastructure library for GOFR projects.

## Overview

This package provides common functionality shared across all GOFR microservices:

- **gofr-dig** - Web scraping and content extraction
- **gofr-plot** - Graph rendering service
- **gofr-np** - Numerical/math operations
- **gofr-doc** - Document generation

## Components

| Module | Description |
|--------|-------------|
| `gofr_common.auth` | JWT authentication service and middleware |
| `gofr_common.logger` | Logging interface and implementations |
| `gofr_common.config` | Configuration management |
| `gofr_common.exceptions` | Base exception classes |
| `gofr_common.mcp` | MCP server utilities and response helpers |
| `gofr_common.web` | Common web middleware (CORS, health checks) |

## Installation

### As a dependency in GOFR projects

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
# For PDF rendering support
uv pip install -e ".[pdf]"

# For plotting support  
uv pip install -e ".[plotting]"

# All optional dependencies
uv pip install -e ".[all]"
```

## Docker Base Image

Build the shared base image used by all GOFR projects:

```bash
cd docker
./build-base.sh
```

This creates `gofr-base:latest` which includes:

- Ubuntu 22.04
- Python 3.11
- UV package manager
- System libraries for PDF/graphics rendering
- Common fonts

## Usage

### Authentication

```python
from gofr_common.auth import AuthService, TokenInfo

# Create auth service with project-specific prefix
auth = AuthService(
    env_prefix="GOFR_DIG",  # Uses GOFR_DIG_JWT_SECRET env var
    token_store_path="/path/to/tokens.json",
)

# Create and verify tokens
token = auth.create_token(group="users")
info: TokenInfo = auth.verify_token(token)
```

### Logging

```python
from gofr_common.logger import ConsoleLogger, Logger

logger = ConsoleLogger(name="my-service")
logger.info("Server started", port=8000, host="0.0.0.0")
```

### Configuration

```python
from gofr_common.config import BaseConfig

config = BaseConfig(env_prefix="GOFR_DIG", project_name="gofr-dig")
data_dir = config.get_data_dir()
auth_dir = config.get_auth_dir()
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Format code
uv run black src tests
uv run ruff check --fix src tests

# Type checking
uv run pyright
```

## License

MIT
