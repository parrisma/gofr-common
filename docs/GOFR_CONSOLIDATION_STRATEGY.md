# GOFR Projects - Technical Consolidation Strategy

**Date:** December 7, 2025  
**Scope:** gofr-dig, gofr-plot, gofr-np, gofr-doc

---

## Overview

This document proposes a technical strategy for extracting and sharing common elements across the four GOFR projects. Based on the analysis in `GOFR_COMMON_ELEMENTS.md`, approximately 3,500+ lines of code are duplicated.

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

## Proposed Architecture

```
devroot/
├── gofr-common/              # NEW: Shared library repository
│   ├── pyproject.toml
│   ├── src/
│   │   └── gofr_common/
│   │       ├── __init__.py
│   │       ├── auth/
│   │       ├── logger/
│   │       ├── config/
│   │       ├── exceptions/
│   │       ├── mcp/
│   │       └── web/
│   ├── docker/
│   │   └── Dockerfile.base
│   └── scripts/
│       └── templates/
│
├── gofr-dig/
│   ├── lib/                  # Git submodule → gofr-common
│   ├── app/                  # Project-specific code only
│   └── pyproject.toml        # Depends on lib/gofr-common
│
├── gofr-plot/
│   ├── lib/                  # Git submodule → gofr-common
│   ├── app/
│   └── pyproject.toml
│
├── gofr-np/
│   ├── lib/                  # Git submodule → gofr-common
│   ├── app/
│   └── pyproject.toml
│
└── gofr-doc/
    ├── lib/                  # Git submodule → gofr-common
    ├── app/
    └── pyproject.toml
```

---

## Implementation Plan

### Phase 1: Create gofr-common Repository (Week 1-2)

#### Step 1.1: Initialize Repository

```bash
cd ~/devroot
mkdir gofr-common
cd gofr-common
git init
```

#### Step 1.2: Create Package Structure

```
gofr-common/
├── pyproject.toml
├── README.md
├── src/
│   └── gofr_common/
│       ├── __init__.py
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── service.py      # Generic AuthService
│       │   └── middleware.py   # Generic middleware
│       ├── logger/
│       │   ├── __init__.py
│       │   ├── interface.py    # Logger ABC
│       │   ├── console.py      # ConsoleLogger
│       │   └── default.py      # Default logger factory
│       ├── config/
│       │   ├── __init__.py
│       │   └── base.py         # BaseConfig class
│       ├── exceptions/
│       │   ├── __init__.py
│       │   └── base.py         # GofrError base classes
│       ├── mcp/
│       │   ├── __init__.py
│       │   ├── server.py       # MCP server scaffolding
│       │   └── responses.py    # Common response helpers
│       └── web/
│           ├── __init__.py
│           └── middleware.py   # CORS, health checks
├── docker/
│   ├── Dockerfile.base
│   └── entrypoint-template.sh
└── scripts/
    ├── restart_servers_template.sh
    └── token_manager.py
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

### Phase 2: Parameterize Common Code (Week 2-3)

#### Step 2.1: Parameterized Auth Service

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

#### Step 2.2: Parameterized Config

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

#### Step 2.3: Parameterized Logger

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

### Phase 3: Add Submodules to Projects (Week 3-4)

#### Step 3.1: Add Submodule to Each Project

```bash
# In each project directory
cd ~/devroot/gofr-dig
git submodule add ../gofr-common lib/gofr-common
git submodule update --init --recursive

# Repeat for gofr-plot, gofr-np, gofr-doc
```

#### Step 3.2: Update pyproject.toml in Each Project

```toml
# gofr-dig/pyproject.toml
[project]
name = "gofr-dig"
version = "0.2.0"
dependencies = [
    # Project-specific dependencies
    "html2text>=2025.4.15",
    "weasyprint>=67.0",
    "aiohttp>=3.9.0",
    "beautifulsoup4>=4.12.0",
    "curl_cffi>=0.7.0",
]

[tool.uv]
# Install gofr-common from local submodule in editable mode
dev-dependencies = [
    "gofr-common @ file:./lib/gofr-common",
    "pytest>=7.0.0",
    # ...
]
```

#### Step 3.3: Update Imports in Each Project

```python
# Before (gofr-dig/app/auth/service.py - DELETE THIS FILE)
from app.logger import Logger, session_logger
class AuthService:
    ...

# After (gofr-dig/app/auth/__init__.py)
from gofr_common.auth import AuthService, TokenInfo
from gofr_common.auth.middleware import verify_token, init_auth_service

# Configure with project-specific prefix
def get_auth_service(
    secret_key: Optional[str] = None,
    token_store_path: Optional[str] = None
) -> AuthService:
    return AuthService(
        env_prefix="GOFR_DIG",
        secret_key=secret_key,
        token_store_path=token_store_path,
    )
```

---

### Phase 4: Migrate Docker Infrastructure (Week 4)

#### Step 4.1: Use Shared Dockerfile.base

```dockerfile
# gofr-dig/docker/Dockerfile.dev
# Reference the shared base image
FROM gofr-base:latest

# Project-specific setup
WORKDIR /home/gofr/devroot/gofr-dig
COPY --chown=gofr:gofr . .

# ...
```

#### Step 4.2: Build Script Updates

```bash
# gofr-common/docker/build-base.sh
#!/bin/bash
docker build -t gofr-base:latest -f docker/Dockerfile.base .

# gofr-dig/docker/build-dev.sh
#!/bin/bash
# Ensure base image exists
if ! docker image inspect gofr-base:latest >/dev/null 2>&1; then
    echo "Building base image..."
    (cd ../gofr-common && ./docker/build-base.sh)
fi

docker build -t gofr-dig-dev:latest -f docker/Dockerfile.dev .
```

---

### Phase 5: Testing & Validation (Week 5)

#### Step 5.1: Create Shared Test Fixtures

```python
# gofr-common/tests/conftest.py
import pytest
from gofr_common.auth import AuthService
from gofr_common.logger import ConsoleLogger

@pytest.fixture
def test_logger():
    return ConsoleLogger(name="test", level=logging.DEBUG)

@pytest.fixture
def test_auth_service(tmp_path, test_logger):
    return AuthService(
        env_prefix="TEST",
        secret_key="test-secret-key",
        token_store_path=str(tmp_path / "tokens.json"),
        logger=test_logger,
    )
```

#### Step 5.2: Run All Project Tests

```bash
# Test gofr-common independently
cd ~/devroot/gofr-common
uv run pytest

# Test each project with the submodule
cd ~/devroot/gofr-dig
git submodule update --init
uv run pytest

# Repeat for all projects
```

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

```
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

```
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

- [ ] Add gofr-common as submodule
- [ ] Update pyproject.toml dependencies
- [ ] Replace app/auth/ with imports from gofr_common
- [ ] Replace app/logger/ with imports from gofr_common
- [ ] Replace app/config.py with parameterized BaseConfig
- [ ] Replace app/exceptions/base.py with gofr_common exceptions
- [ ] Update Docker files to use shared base
- [ ] Update scripts to use templates
- [ ] Run full test suite
- [ ] Update documentation

### gofr-common Setup

- [ ] Create repository
- [ ] Extract and parameterize auth code
- [ ] Extract and parameterize logger code
- [ ] Extract and parameterize config code
- [ ] Extract exception base classes
- [ ] Create Dockerfile.base
- [ ] Create script templates
- [ ] Write comprehensive tests
- [ ] Tag v1.0.0 release

---

## Estimated Effort

| Phase | Duration | Effort |
|-------|----------|--------|
| Phase 1: Create gofr-common | 1-2 weeks | 20-30 hours |
| Phase 2: Parameterize code | 1 week | 15-20 hours |
| Phase 3: Add submodules | 1 week | 10-15 hours |
| Phase 4: Docker migration | 3-5 days | 8-12 hours |
| Phase 5: Testing | 1 week | 15-20 hours |
| **Total** | **5-6 weeks** | **70-100 hours** |

---

## Long-Term Benefits

1. **Reduced Maintenance:** Fix bugs once, benefit 4 projects
2. **Consistency:** All projects use identical auth, logging, etc.
3. **Faster Development:** New projects start with proven infrastructure
4. **Better Testing:** Shared code tested more thoroughly
5. **Documentation:** Single source of truth for common patterns

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

## Next Steps

1. **Review this strategy** with team
2. **Create gofr-common repository**
3. **Start with highest-value extraction** (Docker base, Logger)
4. **Migrate one project first** as pilot (suggest gofr-np - simplest)
5. **Iterate and refine** based on pilot experience
6. **Roll out to remaining projects**
