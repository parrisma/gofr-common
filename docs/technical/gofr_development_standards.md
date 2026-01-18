# GOFR Development Standards & Architecture

This document outlines the mandatory development standards, architecture, and workflows for all GOFR projects (`gofr-dig`, `gofr-doc`, `gofr-plot`, `gofr-np`, `gofr-iq`).

**Target Audience**: Developers and AI Agents (LLMs) working on the codebase.

---

## 1. Architecture Overview

The GOFR ecosystem is a set of microservices built on a shared foundation. Consistency is enforced through the `gofr-common` library and standardized development environments.

### The "Commons" (`gofr-common`)

`gofr-common` is the **mandatory** shared infrastructure library. It is NOT just a package; it is the backbone of every service.

**Key Components:**

* **`gofr_common.auth`**: JWT authentication, token management, and permission groups.
* **`gofr_common.logger`**: Standardized structured logging (JSON/Console).
* **`gofr_common.config`**: Base Pydantic configuration models.
* **`gofr_common.mcp`**: Utilities for building Model Context Protocol (MCP) servers.
* **`gofr_common.web`**: FastAPI middleware (CORS, Health Checks, Error Handling).

**Integration Mechanism:**

* In every project, `gofr-common` is included as a **Git Submodule** at `lib/gofr-common`.
* It is installed in **Editable Mode** (`pip install -e lib/gofr-common`).
* This ensures that changes to commons are immediately reflected in the consuming service during development.

---

## 2. Development Environment (Mandatory)

Development **MUST** occur within the standardized Dev Container environment.

* **Base Image**: `gofr-base` (Ubuntu 22.04, Python 3.11, UV package manager).
* **Container Setup**:
  * The `.devcontainer/devcontainer.json` defines the environment.
  * `docker/entrypoint-dev.sh` is the bootstrap script.
  * **Automatic Setup**: The entrypoint automatically creates the virtual environment (`.venv`), installs `gofr-common` in editable mode, and installs project dependencies.

**Implication**: Do not try to manage Python environments manually on your host machine. Use the container.

---

## 3. Standard Scripts (The MANDATE)

**CRITICAL RULE**: Do not invent new workflows or run raw commands (like `pytest` or `uvicorn`) directly. Use the standardized scripts in the `scripts/` directory. These scripts handle environment variables, python paths, and configuration consistency.

### `run_tests.sh`

**MANDATE**: ALWAYS use `./scripts/run_tests.sh` to run tests.

* **Why?**: It sets up the correct `PYTHONPATH` (including `gofr-common`), activates the virtual environment, sets `GOFR_ENV=TEST`, and configures the test database/storage paths.
* **Usage**:

    ```bash
    ./scripts/run_tests.sh                  # Run all tests
    ./scripts/run_tests.sh tests/test_x.py  # Run specific file
    ./scripts/run_tests.sh -k "auth"        # Filter tests
    ./scripts/run_tests.sh --docker         # Run tests INSIDE the container (from host)
    ./scripts/run_tests.sh --coverage       # Generate coverage report
    ```

* **DO NOT** run `pytest` directly. You will likely fail due to missing paths or environment variables.

### `token_manager.sh`

**MANDATE**: Use this script to manage authentication tokens.

* Wraps the shared logic in `gofr-common/scripts/token_manager.sh`.
* **Usage**:

    ```bash
    ./scripts/token_manager.sh create --group users  # Create a token
    ./scripts/token_manager.sh list                  # List active tokens
    ```

### `restart_servers.sh` / `run_*.sh`

* Use these scripts to start the Web and MCP servers with the correct flags and environment variables.

---

## 4. VS Code Configuration (Mandatory)

We enforce a consolidated standard for VS Code configuration to ensure consistent debugging, linting, and developer experience across all projects.

### `launch.json` (Debugging)

* **Standard**: All projects must use the standardized launch configurations for running tests, debugging MCP/Web servers (with/without auth), and utility scripts.
* **Reference**: See **[vscode_launch_standards.md](vscode_launch_standards.md)** for the mandatory template and port mappings.

### `settings.json` (Workspace Settings)

* **Spell Checking**: `cSpell.words` must contain the shared technical vocabulary (e.g., `fastapi`, `pydantic`, `gofr`, `mcpo`) to prevent false positives.
* **Formatting**: Python formatting is handled by `black` and `ruff`.

### `extensions.json` (Recommended Extensions)

* **Standard List**: All projects share a common set of recommended extensions, including:
  * **Python**: `ms-python.python`, `ms-python.vscode-pylance`, `ms-python.debugpy`
  * **Linting/Formatting**: `ms-python.black-formatter`, `charliermarsh.ruff`
  * **Docs**: `njpwerner.autodocstring`, `bierner.markdown-preview-github-styles`
  * **GitHub**: Copilot and Pull Request extensions.
  * **Utils**: `streetsidesoftware.code-spell-checker`.

---

## 5. Project Structure Standard

All GOFR microservices follow this exact structure:

```text
project-name/
├── .devcontainer/      # VS Code Dev Container config
├── app/                # Application Source Code
│   ├── main_web.py     # FastAPI entrypoint
│   ├── main_mcp.py     # MCP entrypoint
│   └── ...
├── docker/             # Dockerfiles (dev, prod, base)
├── lib/
│   └── gofr-common/    # SUBMODULE: Shared library
├── scripts/            # STANDARD SCRIPTS (run_tests.sh, etc.)
├── tests/              # Pytest tests
├── pyproject.toml      # Dependencies (includes gofr-common)
└── readme.md
```

---

## 6. Testing & Quality Guidelines

### Standard Tools

All projects must include the following in `pyproject.toml` (`[dependency-groups.dev]`):

* **`pytest`**: Test runner.
* **`pytest-cov`**: Coverage reporting.
* **`bandit`**: Security linting.

### Configuration Standards (`pyproject.toml`)

* **Coverage**: Must be configured to output HTML (`htmlcov/`) and XML (`coverage.xml`) reports.
* **Bandit**: Must be configured to exclude test directories and skip `B101` (asserts).

### Best Practices

1. **Conftest**: Every project has a `tests/conftest.py` that sets up fixtures.
2. **Data Isolation**: Tests use a temporary directory or a dedicated `test/data` directory, configured via `GOFR_ENV=TEST`.
3. **Mocking**: Use `unittest.mock` or `pytest-mock` to mock external dependencies.
4. **Common Fixtures**: Look for fixtures provided by `gofr-common` for auth and config testing.

---

## Summary for LLMs/Agents

* **Context**: You are working in a microservice architecture.
* **Dependency**: `gofr-common` is present and editable.
* **Action**: When asked to "run tests", invoke `./scripts/run_tests.sh`.
* **Action**: When asked to "fix auth", look in `gofr_common.auth` or the local `token_manager.sh`.
* **Constraint**: Do not modify the project structure or create new setup scripts. Adhere to the existing `scripts/` ecosystem.
