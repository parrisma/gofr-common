# GOFR Projects - Technical Consolidation Strategy

**Date:** December 7, 2025  
**Last Updated:** December 7, 2025  
**Scope:** gofr-dig, gofr-plot, gofr-np, gofr-doc  
**Status:** ✅ PHASE 1-6 COMPLETE

---

## Overview

This document proposes a technical strategy for extracting and sharing common elements across the four GOFR projects. Based on the analysis in `GOFR_COMMON_ELEMENTS.md`, approximately 3,500+ lines of code are duplicated.

---

## Implementation Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Create gofr-common Repository | ✅ Complete |
| Phase 2 | Parameterize Common Code | ✅ Complete |
| Phase 3 | Add Submodules to Projects | ✅ Complete |
| Phase 4 | Migrate Docker Infrastructure | ✅ Complete |
| Phase 5 | Testing & Validation | ✅ Complete |
| Phase 6 | Python Module Migration | ✅ Complete |

### What Has Been Accomplished

1. **gofr-common repository created** with:
   - `src/gofr_common/` Python package (v1.0.0)
   - `docker/Dockerfile.base` - shared base image (Ubuntu 22.04, Python 3.11, UV)
   - `docker/Dockerfile.openwebui` - shared OpenWebUI service
   - `docker/Dockerfile.n8n` - shared n8n service
   - `docs/MIGRATION_GUIDE.md` - step-by-step migration instructions

2. **All 4 GOFR projects migrated** with standardized Docker setup:
   - gofr-np (ports 8020-8022)
   - gofr-dig (ports 8030-8032)
   - gofr-doc (ports 8040-8042)
   - gofr-plot (ports 8050-8052)

3. **Standardized Docker files** across all projects:
   - `Dockerfile.dev` - extends gofr-base:latest
   - `build-dev.sh` - checks for base image, builds project image
   - `run-dev.sh` - network, volume, port args, environment vars
   - `entrypoint-dev.sh` - UV_VENV_CLEAR=1, installs gofr-common from submodule

4. **Removed duplicate Docker files** from individual projects:
   - Dockerfile.base, build-base.sh (now in gofr-common)
   - Dockerfile.openwebui, build-openwebui.sh, run-openwebui.sh (now in gofr-common)
   - Dockerfile.n8n, build-n8n.sh, run-n8n.sh (now in gofr-common)

5. **All containers verified working**:
   - All 4 dev containers running on gofr-net network
   - gofr_common v1.0.0 imports successfully in all containers
   - Standard user `gofr` (UID 1000, GID 1000) across all containers

6. **Python modules migrated to gofr_common**:
   - `gofr_common.auth` - JWT authentication service, middleware, helpers
   - `gofr_common.logger` - Logger ABC, ConsoleLogger, DefaultLogger, StructuredLogger
   - `gofr_common.config` - BaseConfig, Settings, environment-based configuration
   - `gofr_common.exceptions` - GofrError, ValidationError, SecurityError, etc.
   - `gofr_common.mcp` - MCP response helpers (json_text, success, error)
   - `gofr_common.web` - CORS config, middleware, health endpoints, app factories
   - `gofr_common.testing` - Shared pytest fixtures

7. **All projects now re-export from gofr_common**:
   - `app/auth/__init__.py` → re-exports from `gofr_common.auth`
   - `app/logger/__init__.py` → re-exports from `gofr_common.logger`
   - `app/config.py` → extends `gofr_common.config.Config` with project prefix
   - `app/exceptions/__init__.py` → re-exports from `gofr_common.exceptions`
   - MCP/Web servers use `gofr_common.web` for CORS, middleware, health endpoints

8. **Dead code removed** from all projects:
   - Deleted duplicate `interface.py` files from logger modules
   - Deleted local `service.py` and `middleware.py` from gofr-dig auth
   - Deleted redundant test files that tested deleted modules
   - ~600 lines of dead code removed

9. **Comprehensive tests** in gofr-common:
   - 251 tests total
   - `test_auth.py` - 413 lines
   - `test_logger.py` - Logger interface and implementations
   - `test_config.py` - Configuration management
   - `test_exceptions.py` - Exception hierarchy
   - `test_mcp.py` - MCP response helpers
   - `test_web.py` - 36 new web module tests

---

## Recommended Approach: Git Submodules + Shared Python Package

### Why This Approach?

| Option | Pros | Cons |
|--------|------|------|
| **Git Submodules** | Version pinning, local development, no package registry needed | Submodule management complexity |
| Git Subtree | Simpler workflow | History pollution, harder updates |
| Private PyPI Package | Clean dependency management | Requires package registry infrastructure |
| Monorepo | Single source of truth | Major restructuring, CI complexity |

**Recommendation:** Use **Git Submodules** for the shared library, combined with a local editable install pattern.

---

## Current Architecture (Implemented)

```text
devroot/
├── gofr-common/              # ✅ Shared library repository
│   ├── pyproject.toml
│   ├── src/
│   │   └── gofr_common/
│   │       ├── __init__.py   # v1.0.0
│   │       ├── auth/
│   │       ├── logger/
│   │       ├── config/
│   │       ├── exceptions/
│   │       ├── mcp/
│   │       └── web/
│   ├── docker/
│   │   ├── Dockerfile.base       # ✅ Shared base image
│   │   ├── build-base.sh
│   │   ├── Dockerfile.openwebui  # ✅ Shared OpenWebUI
│   │   ├── build-openwebui.sh
│   │   ├── run-openwebui.sh
│   │   ├── Dockerfile.n8n        # ✅ Shared n8n
│   │   ├── build-n8n.sh
│   │   └── run-n8n.sh
│   └── docs/
│       ├── GOFR_COMMON_ELEMENTS.md
│       ├── GOFR_CONSOLIDATION_STRATEGY.md
│       └── MIGRATION_GUIDE.md
│
├── gofr-np/                  # ✅ Migrated (ports 8020-8022)
│   ├── lib/gofr-common       # Git submodule
│   ├── docker/
│   │   ├── Dockerfile.dev
│   │   ├── build-dev.sh
│   │   ├── run-dev.sh
│   │   └── entrypoint-dev.sh
│   ├── app/
│   └── pyproject.toml
│
├── gofr-dig/                 # ✅ Migrated (ports 8030-8032)
│   ├── lib/gofr-common       # Git submodule
│   ├── docker/
│   │   ├── Dockerfile.dev
│   │   ├── build-dev.sh
│   │   ├── run-dev.sh
│   │   └── entrypoint-dev.sh
│   ├── app/
│   └── pyproject.toml
│
├── gofr-doc/                 # ✅ Migrated (ports 8040-8042)
│   ├── lib/gofr-common       # Git submodule
│   ├── docker/
│   │   ├── Dockerfile.dev
│   │   ├── build-dev.sh
│   │   ├── run-dev.sh
│   │   └── entrypoint-dev.sh
│   ├── app/
│   └── pyproject.toml
│
└── gofr-plot/                # ✅ Migrated (ports 8050-8052)
    ├── lib/gofr-common       # Git submodule
    ├── docker/
    │   ├── Dockerfile.dev
    │   ├── build-dev.sh
    │   ├── run-dev.sh
    │   └── entrypoint-dev.sh
    ├── app/
    └── pyproject.toml
```

---

## Implementation Plan

### Phase 1: Create gofr-common Repository ✅ COMPLETE

#### Step 1.1: Initialize Repository ✅

```bash
cd ~/devroot
mkdir gofr-common
cd gofr-common
git init
```

#### Step 1.2: Package Structure ✅

```text
gofr-common/
├── pyproject.toml
├── README.md
├── src/
│   └── gofr_common/
│       ├── __init__.py       # v1.0.0
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── service.py
│       │   └── middleware.py
│       ├── logger/
│       │   ├── __init__.py
│       │   ├── interface.py
│       │   ├── console.py
│       │   └── default.py
│       ├── config/
│       │   ├── __init__.py
│       │   └── base.py
│       ├── exceptions/
│       │   ├── __init__.py
│       │   └── base.py
│       ├── mcp/
│       │   ├── __init__.py
│       │   ├── server.py
│       │   └── responses.py
│       └── web/
│           ├── __init__.py
│           └── middleware.py
├── docker/
│   ├── Dockerfile.base
│   ├── build-base.sh
│   ├── Dockerfile.openwebui
│   ├── build-openwebui.sh
│   ├── run-openwebui.sh
│   ├── Dockerfile.n8n
│   ├── build-n8n.sh
│   └── run-n8n.sh
└── docs/
    └── MIGRATION_GUIDE.md
```

#### Step 1.3: pyproject.toml for gofr-common

```toml
[project]
name = "gofr-common"
version = "1.0.0"
description = "Shared infrastructure for GOFR projects"
requires-python = ">=3.11"
dependencies = [
    "mcp>=0.9.0",
    "pydantic>=2.0",
    "uvicorn>=0.20.0",
    "fastapi>=0.100.0",
    "starlette>=0.27.0",
    "PyJWT>=2.8.0",
    "httpx>=0.24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "pyright>=1.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/gofr_common"]
```

---

### Phase 2: Parameterize Common Code ✅ COMPLETE

#### Step 2.1: Parameterized Auth Service ✅

```python
# src/gofr_common/auth/service.py
class AuthService:
    def __init__(
        self,
        env_prefix: str = "GOFR",           # e.g., "GOFR_DIG", "GOFR_PLOT"
        secret_key: Optional[str] = None,
        token_store_path: Optional[str] = None,
        logger: Optional[Logger] = None,
    ):
        self.env_prefix = env_prefix
        self.logger = logger or get_default_logger(f"{env_prefix.lower()}-auth")
        
        # Resolve secret from env var: {ENV_PREFIX}_JWT_SECRET
        secret = secret_key or os.environ.get(f"{env_prefix}_JWT_SECRET")
        # ... rest of implementation
```

#### Step 2.2: Parameterized Config ✅

```python
# src/gofr_common/config/base.py
class BaseConfig:
    def __init__(self, env_prefix: str, project_name: str):
        self.env_prefix = env_prefix
        self.project_name = project_name
    
    def get_data_dir(self) -> Path:
        env_var = f"{self.env_prefix}_DATA_DIR"
        if env_data := os.environ.get(env_var):
            return Path(env_data)
        return Path(__file__).parent.parent.parent / "data"
    
    # ... other methods
```

#### Step 2.3: Parameterized Logger ✅

```python
# src/gofr_common/logger/console.py
class ConsoleLogger(Logger):
    def __init__(
        self,
        name: str = "gofr",
        level: int = logging.INFO,
        format_string: Optional[str] = None,
    ):
        self._session_id = str(uuid.uuid4())[:8]
        self._logger = logging.getLogger(name)
        # ... implementation
```

---

### Phase 3: Add Submodules to Projects ✅ COMPLETE

#### Step 3.1: Add Submodule to Each Project ✅

```bash
# Completed for all 4 projects:
cd ~/devroot/gofr-np && git submodule add ../gofr-common lib/gofr-common
cd ~/devroot/gofr-dig && git submodule add ../gofr-common lib/gofr-common
cd ~/devroot/gofr-doc && git submodule add ../gofr-common lib/gofr-common
cd ~/devroot/gofr-plot && git submodule add ../gofr-common lib/gofr-common
```

#### Step 3.2: Update .gitignore in Each Project ✅

Each project's `.gitignore` now has:

```text
lib/
!lib/gofr-common
```

#### Step 3.3: entrypoint-dev.sh Installs gofr-common ✅

Each project's entrypoint installs gofr-common from the submodule:

```bash
# entrypoint-dev.sh (standardized across all projects)
COMMON_DIR="$PROJECT_DIR/lib/gofr-common"

if [ -d "$COMMON_DIR" ]; then
    echo "Installing gofr-common (editable)..."
    cd "$PROJECT_DIR"
    uv pip install -e "$COMMON_DIR"
fi
```

---

### Phase 4: Migrate Docker Infrastructure ✅ COMPLETE

#### Step 4.1: Shared Base Image Built ✅

```bash
# Build the shared base image (1.22GB)
cd ~/devroot/gofr-common/docker
./build-base.sh
# Creates: gofr-base:latest
```

#### Step 4.2: Standardized Dockerfile.dev ✅

All 4 projects now use identical format:

```dockerfile
# Example: gofr-dig/docker/Dockerfile.dev
FROM gofr-base:latest

USER root
RUN apt-get update && apt-get install -y \
    gh openssh-server dnsutils net-tools \
    netcat-openbsd telnet lsof htop strace \
    tcpdump vim jq \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/gofr/devroot/gofr-dig/data \
    && mkdir -p /home/gofr/devroot/gofr-common \
    && chown -R gofr:gofr /home/gofr/devroot

COPY docker/entrypoint-dev.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /home/gofr/devroot/gofr-dig
RUN mkdir -p /home/gofr/.ssh && chmod 700 /home/gofr/.ssh
RUN uv venv /home/gofr/devroot/gofr-dig/.venv --python=python3.11

EXPOSE 8030 8031 8032

USER gofr
ENTRYPOINT ["/entrypoint.sh"]
CMD ["tail", "-f", "/dev/null"]
```

#### Step 4.3: Standardized Build and Run Scripts ✅

All projects use identical script format with project-specific ports:

| Project | Container | Ports | Env Prefix |
|---------|-----------|-------|------------|
| gofr-np | gofr-np-dev | 8020-8022 | GOFRNP_ |
| gofr-dig | gofr-dig-dev | 8030-8032 | GOFRDIG_ |
| gofr-doc | gofr-doc-dev | 8040-8042 | GOFRDOC_ |
| gofr-plot | gofr-plot-dev | 8050-8052 | GOFRPLOT_ |

---

### Phase 5: Testing & Validation ✅ COMPLETE

#### Step 5.1: All Containers Verified ✅

```bash
# All 4 containers running and verified:
docker exec gofr-np-dev bash -c 'source .venv/bin/activate && python -c "import gofr_common; print(gofr_common.__version__)"'
# Output: 1.0.0

docker exec gofr-dig-dev bash -c 'source .venv/bin/activate && python -c "import gofr_common; print(gofr_common.__version__)"'
# Output: 1.0.0

docker exec gofr-doc-dev bash -c 'source .venv/bin/activate && python -c "import gofr_common; print(gofr_common.__version__)"'
# Output: 1.0.0

docker exec gofr-plot-dev bash -c 'source .venv/bin/activate && python -c "import gofr_common; print(gofr_common.__version__)"'
# Output: 1.0.0
```

#### Step 5.2: All Changes Committed and Pushed ✅

| Repository | Commit | Status |
|------------|--------|--------|
| gofr-common | `7228a9c` | ✅ Pushed to origin/main |
| gofr-np | `7015759` | ✅ Pushed to origin/main |
| gofr-dig | `1a2fc4b` | ✅ Pushed to origin/main |
| gofr-doc | `53d8eb0` | ✅ Pushed to origin/main |
| gofr-plot | `68291a1` | ✅ Pushed to origin/main |

---

## Alternative: Git Subtree Approach

If submodules feel too complex, consider git subtree:

```bash
# Add subtree (one-time)
cd ~/devroot/gofr-dig
git subtree add --prefix=lib/gofr-common ../gofr-common main --squash

# Pull updates
git subtree pull --prefix=lib/gofr-common ../gofr-common main --squash

# Push changes back (if you modify shared code in project)
git subtree push --prefix=lib/gofr-common ../gofr-common feature-branch
```

**Pros:** No .gitmodules complexity, works offline better  
**Cons:** History can get messy, harder to track shared lib version

---

## Alternative: Monorepo Approach

Restructure everything into a single repository:

```text
gofr-monorepo/
├── packages/
│   ├── common/           # Shared library
│   ├── dig/              # gofr-dig
│   ├── plot/             # gofr-plot
│   ├── np/               # gofr-np
│   └── doc/              # gofr-doc
├── docker/
├── scripts/
└── pyproject.toml        # Workspace config
```

**Pros:** Single source of truth, atomic changes across projects  
**Cons:** Major restructuring, all projects share CI/CD pipeline, potential for unrelated changes

---

## Version Management Strategy

### Semantic Versioning for gofr-common

```text
MAJOR.MINOR.PATCH
  │     │     └── Bug fixes, no API changes
  │     └──────── New features, backward compatible
  └────────────── Breaking API changes
```

### Pinning in Projects

```bash
# Pin to specific commit in submodule
cd ~/devroot/gofr-dig/lib/gofr-common
git checkout v1.2.3
cd ../..
git add lib/gofr-common
git commit -m "Pin gofr-common to v1.2.3"
```

### Update Workflow

```bash
# Update submodule to latest
cd ~/devroot/gofr-dig
git submodule update --remote lib/gofr-common
uv run pytest  # Verify compatibility
git add lib/gofr-common
git commit -m "Update gofr-common to latest"
```

---

## Migration Checklist

### Per-Project Migration

- [x] Add gofr-common as submodule
- [x] Update .gitignore to allow lib/gofr-common
- [x] Update Docker files to use shared base
- [x] Standardize entrypoint-dev.sh
- [x] Standardize build-dev.sh and run-dev.sh
- [x] Remove duplicate Docker files (base, openwebui, n8n)
- [x] Run container and verify gofr_common imports
- [x] Commit and push changes
- [x] Replace app/auth/ with imports from gofr_common
- [x] Replace app/logger/ with imports from gofr_common
- [x] Replace app/config.py with parameterized BaseConfig
- [x] Replace app/exceptions/base.py with gofr_common exceptions
- [x] Migrate MCP servers to use gofr_common.web
- [x] Migrate Web servers to use gofr_common.web
- [x] Remove dead code (duplicate interfaces, unused modules)
- [x] Run full test suite
- [ ] Update documentation (README files)

### gofr-common Setup

- [x] Create repository
- [x] Extract and parameterize auth code
- [x] Extract and parameterize logger code
- [x] Extract and parameterize config code
- [x] Extract exception base classes
- [x] Create MCP response helpers
- [x] Create web module (CORS, middleware, health, app factories)
- [x] Create testing module (shared fixtures)
- [x] Create Dockerfile.base
- [x] Create Dockerfile.openwebui
- [x] Create Dockerfile.n8n
- [x] Tag v1.0.0 release
- [x] Write comprehensive tests (251 tests)

---

## Actual Effort (Completed)

| Phase | Duration | Status |
|-------|----------|--------|
| Phase 1: Create gofr-common | 1 day | ✅ Complete |
| Phase 2: Parameterize code | 1 day | ✅ Complete |
| Phase 3: Add submodules | 1 day | ✅ Complete |
| Phase 4: Docker migration | 1 day | ✅ Complete |
| Phase 5: Testing | 1 day | ✅ Complete |
| Phase 6: Python module migration | 2 days | ✅ Complete |
| **Total** | **~7 days** | **✅ Complete** |

---

## Long-Term Benefits

1. **Reduced Maintenance:** Fix bugs once, benefit 4 projects
2. **Consistency:** All projects use identical auth, logging, etc.
3. **Faster Development:** New projects start with proven infrastructure
4. **Better Testing:** Shared code tested more thoroughly (251 tests)
5. **Documentation:** Single source of truth for common patterns
6. **Dead Code Elimination:** ~600 lines of duplicate code removed

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking changes | Semantic versioning, pinned submodules |
| Learning curve | Documentation, pair programming |
| Circular dependencies | Clear module boundaries |
| Test failures | Parallel testing during migration |
| Docker build issues | Gradual rollout, fallback images |

---

## Remaining Work (Future Phases)

### Phase 7: Documentation & Polish (Optional)

- [ ] Update README.md in each project to reference gofr-common
- [ ] Add architecture diagrams showing shared module usage
- [ ] Document migration patterns for new projects

### Phase 8: Additional Consolidation Opportunities (Optional)

- [ ] Standardize `scripts/restart_servers.sh` across projects
- [ ] Standardize `scripts/token_manager.sh` as CLI tool
- [ ] Consider production Dockerfile standardization
- [ ] Consider CI/CD pipeline standardization

### Phase 9: Error Mapping Consolidation (Optional)

- [ ] Extract common error mapper patterns to gofr_common.errors
- [ ] Standardize MCP error response codes

---

## Current gofr_common Module Structure

```text
gofr_common/
├── __init__.py           # v1.0.0
├── auth/
│   ├── __init__.py       # AuthService, TokenInfo, middleware functions
│   ├── service.py        # JWT-based AuthService with token store
│   ├── middleware.py     # FastAPI/Starlette security integration
│   ├── config.py         # Auth startup configuration helpers
│   └── helpers.py        # Token resolution helpers
├── logger/
│   ├── __init__.py       # Logger ABC, implementations
│   ├── interface.py      # Logger abstract base class
│   ├── console_logger.py # Console logging with session ID
│   ├── default_logger.py # Default logger singleton
│   └── structured_logger.py # JSON structured logging
├── config/
│   ├── __init__.py       # Config, Settings, get_settings
│   ├── base.py           # BaseConfig with environment prefixes
│   └── settings.py       # Pydantic Settings models
├── exceptions/
│   ├── __init__.py       # All exception classes
│   └── base.py           # GofrError hierarchy
├── mcp/
│   ├── __init__.py       # MCP response helpers
│   └── responses.py      # json_text, success, error helpers
├── web/
│   ├── __init__.py       # All web exports
│   ├── cors.py           # CORSConfig with factory methods
│   ├── middleware.py     # AuthHeaderMiddleware, RequestLoggingMiddleware
│   ├── health.py         # ping/health response and route helpers
│   └── app.py            # create_starlette_app, create_mcp_starlette_app
└── testing/
    ├── __init__.py       # Shared fixtures
    └── pytest_fixtures.py # Common test fixtures
```

---

## Project Re-export Pattern

Each project maintains backward compatibility through re-exports:

```python
# app/auth/__init__.py
from gofr_common.auth import (
    AuthService, TokenInfo, get_auth_service,
    verify_token, optional_verify_token, init_auth_service,
)

# app/logger/__init__.py  
from gofr_common.logger import Logger
from .console_logger import ConsoleLogger  # Project-specific config
from .default_logger import DefaultLogger

# app/config.py
from gofr_common.config import Config as BaseConfig
class Config(BaseConfig):
    _env_prefix = "GOFR_NP"  # Project-specific prefix

# app/exceptions/__init__.py
from gofr_common.exceptions import GofrError, ValidationError, ...
GofrNpError = GofrError  # Alias for backward compatibility
```
