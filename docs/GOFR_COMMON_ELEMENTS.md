# GOFR Projects - Common Elements Analysis

**Analysis Date:** December 6, 2025  
**Projects Analyzed:** gofr-dig, gofr-plot, gofr-np, gofr-doc

---

## Executive Summary

All four GOFR projects share substantial common infrastructure that is currently duplicated across repositories. This analysis identifies reusable components that can be extracted into shared libraries to reduce duplication, improve maintainability, and ensure consistency.

**Key Finding:** Approximately **40-50%** of the codebase is identical or nearly identical across projects, representing significant opportunity for consolidation.

---

## 1. Authentication & Authorization Infrastructure

### Common Components

#### 1.1 JWT Authentication Service (`app/auth/service.py`)
- **Similarity:** 85-95% identical across all projects
- **Core Functionality:**
  - JWT token creation and validation
  - Token-group mapping and persistence
  - Token store management (JSON file-based)
  - Session tracking
- **Minor Differences:**
  - Environment variable names (e.g., `GOFR_DIG_JWT_SECRET` vs `GOFR_PLOT_JWT_SECRET`)
  - gofr-plot has additional features: in-memory mode, secret fingerprinting
  - Default logger name varies

**Recommendation:** Extract to shared library with configurable environment prefix

#### 1.2 Authentication Middleware (`app/auth/middleware.py`)
- **Similarity:** 75-85% identical
- **Core Functionality:**
  - FastAPI/Starlette security integration
  - Token verification from HTTP headers
  - Optional authentication support
  - Global auth service management
- **Minor Differences:**
  - gofr-plot has device fingerprinting and security auditor integration
  - Logging verbosity varies

**Recommendation:** Extract with plugin architecture for extended features

#### 1.3 Startup Auth Configuration (`app/startup/auth_config.py`)
- **Similarity:** 70-80% identical
- **Core Functionality:**
  - Resolve JWT secret from CLI args, environment, or auto-generation
  - Resolve token store path with fallbacks
  - Consistent priority chain handling
- **Minor Differences:**
  - Environment variable names
  - Error handling strategies (some exit, some raise exceptions)

**Recommendation:** Extract with parameterized environment variable prefixes

---

## 2. Logging Infrastructure

### Common Components

#### 2.1 Logger Interface (`app/logger/interface.py`)
- **Similarity:** 100% identical across all projects
- **Interface Methods:**
  - `debug()`, `info()`, `warning()`, `error()`, `critical()`
  - `get_session_id()`
- **Usage:** Abstract base class for all logger implementations

**Recommendation:** Perfect candidate for shared library - zero customization needed

#### 2.2 Console Logger (`app/logger/console_logger.py`)
- **Similarity:** 95% identical
- **Core Functionality:**
  - Python logging module wrapper
  - Session ID tracking via UUID
  - Structured logging with kwargs
  - Configurable format strings
- **Minor Differences:**
  - Default logger name (e.g., "gofr-dig" vs "gofr-plot")

**Recommendation:** Extract with configurable logger name parameter

#### 2.3 Default Logger (`app/logger/default_logger.py`)
- **Similarity:** 100% identical (where present)
- **Functionality:** Provides session-scoped logger singleton

**Recommendation:** Extract to shared library

---

## 3. Configuration Management

### Common Components

#### 3.1 Config Class (`app/config.py`)
- **Similarity:** 85-90% identical (gofr-dig, gofr-np, gofr-doc)
- **Core Functionality:**
  - Data directory resolution
  - Storage, auth, sessions directory paths
  - Test mode support with temporary directories
  - Environment variable overrides
- **Minor Differences:**
  - Environment variable names (e.g., `GOFR_DIG_DATA_DIR` vs `GOFRNP_DATA_DIR`)
  - Project-specific directory structure assumptions
- **Note:** gofr-plot has evolved to use a settings module, but maintains backward compatibility

**Recommendation:** Extract with parameterized prefixes and directory structure

---

## 4. Exception Handling

### Common Components

#### 4.1 Base Exception Classes (`app/exceptions/base.py`)
- **Similarity:** 90-95% identical
- **Common Classes:**
  - `GofrXxxError` (base exception with structured error info)
  - `ValidationError`
  - `ResourceNotFoundError`
  - `SecurityError`
  - `ConfigurationError`
  - `RegistryError`
- **Minor Differences:**
  - Base exception name varies by project (GofrDigError, GofrNpError, GofrDocError)
  - gofr-doc has additional domain-specific exceptions

**Recommendation:** Extract as generic base classes with project-specific naming

#### 4.2 Error Mapping (`app/errors/mapper.py`)
- **Similarity:** Present in gofr-dig, gofr-np, gofr-doc
- **Functionality:**
  - Maps exceptions to MCP-compatible error responses
  - Provides recovery strategies
  - Error code standardization

**Recommendation:** Extract with extensible error code registry

---

## 5. MCP Server Infrastructure

### Common Components

#### 5.1 MCP Server Structure (`app/mcp_server/mcp_server.py`)
- **Similarity:** 60-70% structural similarity
- **Common Patterns:**
  - Streamable HTTP transport setup
  - Tool registration and invocation
  - CORS middleware configuration
  - Authentication integration
  - Health check (`ping`) tool
  - JSON response helpers (`_json_text()`, `_error()`, `_success()`)
- **Differences:**
  - Domain-specific tools and handlers
  - Response formats and data models

**Recommendation:** Extract common server scaffolding, tool registry, and response helpers

#### 5.2 MCP Tool Patterns
- **Common Tool Structure:**
  - `@app.list_tools()` decorator pattern
  - `@app.call_tool()` decorator pattern
  - Pydantic validation models
  - Structured error responses

**Recommendation:** Create MCP tool framework with common patterns and utilities

---

## 6. Web Server Infrastructure

### Common Components

#### 6.1 Web Server Structure (`app/web_server/web_server.py`)
- **Similarity:** 50-60% structural similarity
- **Common Patterns:**
  - FastAPI/Starlette application setup
  - CORS middleware configuration
  - Authentication integration
  - Health check endpoints (`/ping`, `/health`)
  - JWT token verification on endpoints
- **Differences:**
  - Domain-specific endpoints and handlers
  - gofr-dig and gofr-np are minimal stubs
  - gofr-plot and gofr-doc have full-featured implementations

**Recommendation:** Extract common web server scaffolding and middleware

---

## 7. Docker Infrastructure

### Common Components

#### 7.1 Base Dockerfile (`docker/Dockerfile.base`)
- **Similarity:** 100% identical across all projects
- **Components:**
  - Ubuntu 22.04 base
  - System dependency installation
  - Python 3.11 installation
  - UV package manager setup
  - Font installation for matplotlib/PDF rendering
  - User/group cleanup

**Recommendation:** **HIGHEST PRIORITY** - Use single shared Dockerfile.base

#### 7.2 Development Entrypoint (`docker/entrypoint-dev.sh`)
- **Similarity:** 85-90% identical
- **Functionality:**
  - Data directory permission fixes
  - Virtual environment setup
  - Dependency installation from pyproject.toml/requirements.txt
- **Minor Differences:**
  - Project-specific paths
  - User names

**Recommendation:** Extract with parameterized paths and user names

#### 7.3 Build Scripts (`docker/build-*.sh`, `docker/run-*.sh`)
- **Similarity:** 70-80% similar patterns
- **Common Patterns:**
  - Docker build with build args
  - Volume mounting
  - Port mapping
  - Environment variable passing

**Recommendation:** Create templated build/run scripts with project-specific configs

---

## 8. Deployment & Operations Scripts

### Common Components

#### 8.1 Server Restart Scripts (`scripts/restart_servers.sh`)
- **Similarity:** 75-85% identical
- **Common Functionality:**
  - Kill existing server processes
  - Verify port release
  - Start servers in order (MCP → MCPO → Web)
  - Health check verification
  - Environment-based configuration
- **Minor Differences:**
  - Environment variable names
  - Port numbers
  - Project-specific process patterns

**Recommendation:** Extract with configuration file-based customization

#### 8.2 Token Manager Scripts (`scripts/token_manager.sh`)
- **Similarity:** 90-95% identical (where present)
- **Functionality:**
  - JWT token creation
  - Token listing
  - Token revocation
  - Token store management

**Recommendation:** Extract as shared CLI tool

---

## 9. Testing Infrastructure

### Common Components

#### 9.1 Pytest Configuration (`pyproject.toml` - tool.pytest.ini_options)
- **Similarity:** 95% identical
- **Common Settings:**
  - `asyncio_mode = "auto"`
  - `pythonpath = ["."]`
  - Common filterwarnings

**Recommendation:** Extract as shared pytest configuration template

#### 9.2 Test Structure
- **Common Patterns:**
  - `test/` directory structure
  - Async test patterns
  - Fixture patterns for auth, logging, temp directories

**Recommendation:** Create shared test utilities and fixtures library

---

## 10. Build & Packaging Configuration

### Common Components

#### 10.1 Project Metadata (`pyproject.toml`)
- **Similarity:** 70-80% identical
- **Common Configuration:**
  - Python >= 3.11 requirement
  - Build system (hatchling)
  - Black formatter config (line-length = 100)
  - Ruff linter config
  - UV dev dependencies
  - Common core dependencies: mcp, pydantic, uvicorn, fastapi, starlette, PyJWT

**Recommendation:** Create shared pyproject.toml template with project-specific overlays

#### 10.2 Common Dependencies
- **Universal Across All Projects:**
  - `mcp>=0.9.0`
  - `pydantic>=2.0`
  - `uvicorn>=0.20.0`
  - `fastapi>=0.100.0`
  - `starlette>=0.27.0`
  - `PyJWT>=2.8.0`
  - `httpx>=0.24.0`
  - `mcpo>=0.0.19`
  - `pyright>=1.1.0`

**Recommendation:** Define shared dependency groups

---

## 11. Git & Development Configuration

### Common Components

#### 11.1 Git Ignore Patterns (`.gitignore`)
- **Common Patterns:**
  - Python cache (`__pycache__/`, `*.pyc`)
  - Virtual environments (`.venv/`)
  - IDE configs (`.vscode/`)
  - Test caches (`.pytest_cache/`, `.ruff_cache/`)
  - Data directories (`data/`)
  - Logs (`logs/`, `*.log`)

**Recommendation:** Create shared .gitignore template

#### 11.2 VS Code Configuration (`.vscode/`)
- **Common Settings:**
  - Python interpreter path
  - Formatting settings
  - Linting configuration

**Recommendation:** Create shared VS Code workspace template

---

## Summary of Extractable Components

### Priority 1 (Immediate High Value)
1. **Docker base image** - 100% identical, used by all projects
2. **Logger infrastructure** - 95%+ identical, core dependency
3. **Auth service** - 85%+ identical, security-critical
4. **Exception base classes** - 90%+ identical, contracts

### Priority 2 (High Value)
5. **Configuration management** - 85%+ identical
6. **MCP server scaffolding** - Common patterns and utilities
7. **Token manager utilities** - 90%+ identical
8. **Build/deployment scripts** - 75%+ identical patterns

### Priority 3 (Medium Value)
9. **Web server scaffolding** - Common middleware and patterns
10. **Test utilities and fixtures** - Shared testing infrastructure
11. **Project templates** - pyproject.toml, .gitignore, etc.

---

## Quantitative Analysis

| Component Category | Lines of Code (Duplicated) | Similarity % | Projects Affected |
|-------------------|---------------------------|--------------|-------------------|
| Auth Infrastructure | ~800 lines | 85% | All 4 |
| Logger Infrastructure | ~300 lines | 95% | All 4 |
| Config Management | ~400 lines | 85% | All 4 |
| Exception Handling | ~300 lines | 90% | All 4 |
| Docker Infrastructure | ~200 lines | 100% | All 4 |
| MCP Scaffolding | ~500 lines | 60% | All 4 |
| Scripts/Tooling | ~1000 lines | 80% | All 4 |
| **TOTAL** | **~3,500 lines** | **82% avg** | **All 4** |

**Total Duplicated Code:** Approximately 3,500-4,000 lines across all projects  
**Maintenance Burden:** Any bug fix or enhancement requires 4x the effort

---

## Risk Assessment

### Risks of Current Duplication
1. **Inconsistent Security:** Bug fixes in auth must be applied 4 times
2. **Drift Over Time:** Projects diverging despite identical requirements
3. **Testing Burden:** Core infrastructure tested 4 times independently
4. **Onboarding Friction:** New developers must learn 4 versions of same code

### Risks of Consolidation
1. **Breaking Changes:** Refactoring may introduce regressions
2. **Dependency Hell:** Shared library version conflicts
3. **Coordination Overhead:** Changes require multi-repo coordination
4. **Over-Abstraction:** Generic solutions may be less intuitive

**Mitigation:** Phased approach, comprehensive testing, semantic versioning

---

## Next Steps

See `GOFR_CONSOLIDATION_STRATEGY.md` for detailed technical strategy and implementation roadmap.
