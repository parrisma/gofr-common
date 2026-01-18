# GOFR Authentication System

This document provides a comprehensive guide to the GOFR authentication system, consolidating information from source code, existing documentation, and migration guides. It is designed for both LLMs and human developers to understand, implement, and use the system effectively.

## 1. System Overview

The GOFR authentication system is a robust, multi-group, JWT-based authentication framework designed for microservices. It moves beyond simple single-group tokens to a flexible access control model with pluggable storage backends.

### Core Philosophy

*   **Multi-Group Access:** A single token can grant access to multiple groups (e.g., `["admin", "users", "reporting"]`).
*   **Soft-Delete Architecture:** Nothing is ever truly deleted. Groups are made "defunct", and tokens are "revoked". This ensures a complete audit trail.
*   **Pluggable Storage:** Supports Memory (testing), File (single-instance), and HashiCorp Vault (production) backends via a protocol-based abstraction.
*   **Reserved Groups:** System-critical groups (`public`, `admin`) are protected and cannot be disabled.
*   **Dependency Injection:** Designed for modern frameworks like FastAPI, avoiding global state where possible.

## 2. Architecture & Components

The system is composed of several key layers:

### 2.1. Data Models

*   **`TokenRecord`**: The server-side representation of a token.
    *   Keyed by UUID (`jti`).
    *   Stores: `groups`, `status` ("active"/"revoked"), `created_at`, `expires_at`, `revoked_at`, `fingerprint`.
*   **`Group`**: Represents a permission scope or content source.
    *   Keyed by UUID.
    *   Stores: `name` (unique), `description`, `is_active`, `defunct_at`, `is_reserved`.
*   **`TokenInfo`**: The runtime object returned after token verification.
    *   Contains: `token` string, `groups` list, `expires_at`, `issued_at`.

### 2.2. Services

*   **`TokenService`**: Handles low-level JWT operations (create, verify, revoke). It is unaware of group semantics beyond storing the list of strings.
*   **`GroupRegistry`**: Manages the lifecycle of groups. It ensures reserved groups exist and handles soft-deletion.
*   **`AuthService`**: The high-level orchestrator. It combines `TokenService` and `GroupRegistry` to provide a complete authentication API. It validates that groups exist before creating tokens.
*   **`AuthProvider`**: A dependency injection wrapper for FastAPI. It exposes methods like `verify_token` and `require_group` as dependencies.

### 2.3. Storage Backends

The system uses `TokenStore` and `GroupStore` protocols to abstract data persistence.

| Backend | Use Case | Persistence | Shared State |
| :--- | :--- | :--- | :--- |
| **Memory** | Unit testing, local dev | None (process lifetime) | No |
| **File** | Single-instance deployments | JSON files | No |
| **Vault** | Production, multi-instance | HashiCorp Vault (KV v2) | Yes |

## 3. Implementation Guide

### 3.1. Initialization

The recommended way to initialize the system is using the factory pattern which reads from environment variables.

```python
from gofr_common.auth import create_stores_from_env, AuthService, GroupRegistry, AuthProvider

# 1. Create stores based on env vars (GOFR_AUTH_BACKEND, etc.)
token_store, group_store = create_stores_from_env(prefix="GOFR_DIG")

# 2. Initialize registry and service
groups = GroupRegistry(store=group_store)
auth_service = AuthService(
    token_store=token_store,
    group_registry=groups,
    env_prefix="GOFR_DIG" # Will read GOFR_DIG_JWT_SECRET
)

# 3. Create provider for FastAPI
auth_provider = AuthProvider(auth_service)
```

### 3.2. FastAPI Integration

Use the `AuthProvider` to inject security dependencies.

```python
from fastapi import FastAPI, Depends
from gofr_common.auth import TokenInfo

app = FastAPI()

# Protect a route
@app.get("/protected")
def protected_route(token: TokenInfo = Depends(auth_provider.verify_token)):
    return {"user_groups": token.groups}

# Require specific group
@app.post("/admin/users")
def create_user(token: TokenInfo = Depends(auth_provider.require_admin)):
    return {"status": "User created"}

# Require custom group
@app.get("/finance/report")
def get_report(token: TokenInfo = Depends(auth_provider.require_group("finance"))):
    return {"data": "..."}
```

### 3.3. Creating Tokens (Scripting)

Tokens are typically created via management scripts, not by the application itself (except for login endpoints).

```python
# Create a token for specific groups
token = auth_service.create_token(
    groups=["finance", "reporting"],
    expires_in_seconds=86400 * 30 # 30 days
)
print(f"Generated Token: {token}")
```

## 4. Configuration Reference

The system is configured primarily via environment variables. Replace `{PREFIX}` with your project prefix (e.g., `GOFR_DIG`, `GOFR_IQ`).

| Variable | Description | Default | Required |
| :--- | :--- | :--- | :--- |
| `{PREFIX}_JWT_SECRET` | Secret key for signing JWTs | - | Yes (Prod) |
| `{PREFIX}_AUTH_BACKEND` | Storage backend: `memory`, `file`, `vault` | `memory` | No |
| `{PREFIX}_TOKEN_STORE` | Path to tokens JSON file (File backend) | `data/auth/tokens.json` | No |
| `{PREFIX}_GROUP_STORE` | Path to groups JSON file (File backend) | `data/auth/groups.json` | No |
| `{PREFIX}_VAULT_URL` | Vault server URL | `http://localhost:8200` | If Vault |
| `{PREFIX}_VAULT_TOKEN` | Vault auth token | - | If Vault |
| `{PREFIX}_VAULT_PATH_PREFIX` | Path prefix in Vault KV | `gofr/auth` | No |

## 5. CLI Management Tool

The `auth_manager.py` script provides a unified command-line interface for managing groups and tokens.

### Usage

```bash
# List all groups
python scripts/auth_manager.py groups list

# Create a new group
python scripts/auth_manager.py groups create finance --description "Finance Team"

# Make a group defunct (soft delete)
python scripts/auth_manager.py groups defunct finance

# List all tokens
python scripts/auth_manager.py tokens list

# Create a new token
python scripts/auth_manager.py tokens create --groups admin,finance --expires 86400

# Revoke a token
python scripts/auth_manager.py tokens revoke <token-id>

# Inspect a token string
python scripts/auth_manager.py tokens inspect <token-string>
```

### Environment Variables for CLI

*   `GOFR_AUTH_BACKEND`: Storage backend (`file`, `memory`, `vault`)
*   `GOFR_AUTH_DATA_DIR`: Directory for auth data (default: `data/auth`)
*   `GOFR_JWT_SECRET`: JWT signing secret

## 6. Migration from Legacy Version

If upgrading from the old single-group auth system:

1.  **Update Code:** Replace `auth.create_token(group="x")` with `auth.create_token(groups=["x"])`.
2.  **Update Checks:** Replace `token.group == "x"` with `token.has_group("x")`.
3.  **Migrate Data:** The storage format has changed (JWT key vs UUID key). Old tokens are incompatible. You must issue new tokens.
4.  **Bootstrap:** Ensure `init_auth.py` is run or `GroupRegistry` is initialized to create the `admin` and `public` groups.

## 7. Developer Cheatsheet

*   **I need to add a new permission:** Create a new group (e.g., `billing_read`).
*   **I need to give a service access:** Issue a token with the required groups.
*   **I need to revoke access:** Use `revoke_token(token_string)`. The token will be marked revoked immediately.
*   **I need to test locally:** Use `GOFR_AUTH_BACKEND=memory` or `token_store_path=":memory:"`.
*   **I need to debug a token:** Decode the JWT. Look at the `jti` (UUID). Find that UUID in your `tokens.json` or Vault to see its server-side status.

---

## 8. Phased Improvement Plan

This section outlines a test-driven plan to address the usability gaps identified in Section 5.

### Phase 1: Group Validation on Verify (High Priority)

**Problem:** Tokens continue to work after their groups are made defunct.

**Solution:** Add `validate_groups` parameter to `verify_token()`.

**Implementation:**

```python
# In service.py - AuthService.verify_token()
def verify_token(
    self,
    token: str,
    fingerprint: Optional[str] = None,
    require_store: bool = True,
    validate_groups: bool = False,  # NEW PARAMETER
) -> TokenInfo:
    # ... existing verification logic ...
    
    if validate_groups:
        for group_name in groups:
            group = self._group_registry.get_group_by_name(group_name)
            if group is None:
                raise InvalidGroupError(f"Group '{group_name}' does not exist")
            if not group.is_active:
                raise InvalidGroupError(f"Group '{group_name}' is defunct")
    
    return TokenInfo(...)
```

**Tests to Add (`tests/test_auth_phase1.py`):**

```python
class TestGroupValidationOnVerify:
    """Phase 1: Group validation at verification time."""

    def test_verify_passes_without_validation_after_group_defunct(self):
        """Token still works when validate_groups=False (default)."""
        auth = create_memory_auth()
        group = auth.groups.create_group("temp-group")
        token = auth.create_token(groups=["temp-group"])
        
        # Make group defunct
        auth.groups.make_defunct(group.id)
        
        # Should still verify with default settings
        info = auth.verify_token(token, validate_groups=False)
        assert "temp-group" in info.groups

    def test_verify_fails_with_validation_after_group_defunct(self):
        """Token fails verification when validate_groups=True and group defunct."""
        auth = create_memory_auth()
        group = auth.groups.create_group("temp-group")
        token = auth.create_token(groups=["temp-group"])
        
        auth.groups.make_defunct(group.id)
        
        with pytest.raises(InvalidGroupError, match="defunct"):
            auth.verify_token(token, validate_groups=True)

    def test_verify_fails_with_validation_when_group_deleted_from_store(self):
        """Token fails if group was somehow removed from store."""
        auth = create_memory_auth()
        auth.groups.create_group("ephemeral")
        token = auth.create_token(groups=["ephemeral"])
        
        # Simulate group disappearing (shouldn't happen, but defensive)
        auth.groups._store._store.clear()
        auth.groups.ensure_reserved_groups()  # Re-add reserved only
        
        with pytest.raises(InvalidGroupError, match="does not exist"):
            auth.verify_token(token, validate_groups=True)

    def test_reserved_groups_always_valid(self):
        """Reserved groups (admin, public) always pass validation."""
        auth = create_memory_auth()
        token = auth.create_token(groups=["admin"])
        
        # Should always work
        info = auth.verify_token(token, validate_groups=True)
        assert "admin" in info.groups
```

**Acceptance Criteria:**
- [ ] `validate_groups` parameter added to `AuthService.verify_token()`
- [ ] `validate_groups` parameter added to `AuthProvider.verify_token()`
- [ ] All 4 tests pass
- [ ] Existing tests still pass (backward compatible)

---

### Phase 2: File Backend Caching (Medium Priority)

**Problem:** `FileTokenStore` and `FileGroupStore` read from disk on every operation.

**Solution:** Add mtime-based caching - only reload when file has changed.

**Implementation:**

```python
# In backends/file.py
class FileTokenStore:
    def __init__(self, path, logger=None):
        self.path = Path(path)
        self._store: Dict[str, TokenRecord] = {}
        self._last_mtime: float = 0.0  # NEW
        self._load()

    def _needs_reload(self) -> bool:
        """Check if file was modified since last load."""
        if not self.path.exists():
            return len(self._store) > 0  # Clear cache if file deleted
        try:
            current_mtime = self.path.stat().st_mtime
            return current_mtime > self._last_mtime
        except OSError:
            return True

    def _load(self) -> None:
        if self.path.exists():
            self._last_mtime = self.path.stat().st_mtime
            # ... existing load logic ...

    def reload(self) -> None:
        """Reload only if file changed."""
        if self._needs_reload():
            self._load()
```

**Tests to Add (`tests/test_backends_phase2.py`):**

```python
class TestFileStoreCaching:
    """Phase 2: Efficient file backend caching."""

    def test_reload_skipped_when_file_unchanged(self, tmp_path):
        """Reload is a no-op when file hasn't changed."""
        store = FileTokenStore(tmp_path / "tokens.json")
        record = TokenRecord.create(groups=["test"])
        store.put(str(record.id), record)
        
        initial_mtime = store._last_mtime
        store.reload()
        
        assert store._last_mtime == initial_mtime  # Didn't re-read

    def test_reload_triggered_when_file_modified(self, tmp_path):
        """Reload reads file when mtime changes."""
        path = tmp_path / "tokens.json"
        store = FileTokenStore(path)
        record = TokenRecord.create(groups=["test"])
        store.put(str(record.id), record)
        
        # Simulate external modification
        import time
        time.sleep(0.01)  # Ensure mtime differs
        path.write_text('{}')  # External clear
        
        store.reload()
        assert len(store) == 0  # Picked up external change

    def test_get_uses_cached_data(self, tmp_path):
        """Get operations don't trigger reload."""
        store = FileTokenStore(tmp_path / "tokens.json")
        record = TokenRecord.create(groups=["test"])
        store.put(str(record.id), record)
        
        # Multiple gets shouldn't reload
        for _ in range(10):
            result = store.get(str(record.id))
            assert result is not None

    def test_concurrent_write_detected(self, tmp_path):
        """Changes from another process are detected on reload."""
        path = tmp_path / "tokens.json"
        store1 = FileTokenStore(path)
        store2 = FileTokenStore(path)  # Simulates another process
        
        record = TokenRecord.create(groups=["test"])
        store1.put(str(record.id), record)
        
        # Store2 sees it after reload
        store2.reload()
        assert store2.exists(str(record.id))
```

**Acceptance Criteria:**
- [ ] `_needs_reload()` method added to `FileTokenStore` and `FileGroupStore`
- [ ] `reload()` only reads file when mtime changed
- [ ] All 4 tests pass
- [ ] Performance improvement measurable in benchmarks

---

### Phase 3: Token Management CLI (Medium Priority)

**Problem:** `create_group.py` is confusingly named; no easy way to list/manage tokens.

**Solution:** Create unified `auth_manager.py` CLI with clear subcommands.

**Implementation:**

```python
# scripts/auth_manager.py
"""
Unified auth management CLI.

Usage:
    python auth_manager.py groups list
    python auth_manager.py groups create <name> [--description DESC]
    python auth_manager.py groups defunct <name>
    
    python auth_manager.py tokens list [--status active|revoked]
    python auth_manager.py tokens create --groups admin,users [--expires SECONDS]
    python auth_manager.py tokens revoke <token-id>
    python auth_manager.py tokens inspect <token-string>
"""
```

**Tests to Add (`tests/test_cli_phase3.py`):**

```python
class TestAuthManagerCLI:
    """Phase 3: Unified CLI tool tests."""

    def test_groups_list_shows_all_groups(self, tmp_path, capsys):
        """'groups list' displays all groups."""
        # Setup
        result = run_cli(["groups", "list"], data_dir=tmp_path)
        assert result.returncode == 0
        assert "admin" in result.stdout
        assert "public" in result.stdout

    def test_groups_create_new_group(self, tmp_path):
        """'groups create' adds a new group."""
        result = run_cli(["groups", "create", "finance", "--description", "Finance team"], 
                        data_dir=tmp_path)
        assert result.returncode == 0
        
        # Verify it exists
        result = run_cli(["groups", "list"], data_dir=tmp_path)
        assert "finance" in result.stdout

    def test_tokens_list_shows_active_tokens(self, tmp_path):
        """'tokens list' shows tokens with their metadata."""
        # Create a token first
        run_cli(["tokens", "create", "--groups", "admin"], data_dir=tmp_path)
        
        result = run_cli(["tokens", "list"], data_dir=tmp_path)
        assert result.returncode == 0
        assert "admin" in result.stdout
        assert "active" in result.stdout.lower()

    def test_tokens_create_outputs_jwt(self, tmp_path):
        """'tokens create' outputs a valid JWT."""
        result = run_cli(["tokens", "create", "--groups", "admin,users"], 
                        data_dir=tmp_path)
        assert result.returncode == 0
        # JWT format: header.payload.signature
        assert result.stdout.count('.') == 2

    def test_tokens_revoke_by_id(self, tmp_path):
        """'tokens revoke' marks token as revoked."""
        # Create and get token ID
        create_result = run_cli(["tokens", "create", "--groups", "test"], 
                               data_dir=tmp_path)
        
        list_result = run_cli(["tokens", "list", "--format", "json"], 
                             data_dir=tmp_path)
        token_id = json.loads(list_result.stdout)[0]["id"]
        
        # Revoke it
        revoke_result = run_cli(["tokens", "revoke", token_id], data_dir=tmp_path)
        assert revoke_result.returncode == 0
        
        # Verify revoked
        list_result = run_cli(["tokens", "list", "--status", "revoked"], 
                             data_dir=tmp_path)
        assert token_id in list_result.stdout

    def test_tokens_inspect_decodes_jwt(self, tmp_path):
        """'tokens inspect' shows decoded token info."""
        create_result = run_cli(["tokens", "create", "--groups", "admin"], 
                               data_dir=tmp_path)
        token = create_result.stdout.strip()
        
        inspect_result = run_cli(["tokens", "inspect", token], data_dir=tmp_path)
        assert "admin" in inspect_result.stdout
        assert "jti" in inspect_result.stdout
```

**Acceptance Criteria:**
- [ ] `scripts/auth_manager.py` created with subcommand structure
- [ ] All 6 CLI tests pass
- [ ] Help text is clear and comprehensive
- [ ] Old scripts (`create_group.py`) still work (deprecated notice)

---

### Phase 4: Explicit Public Group Handling (Low Priority)

**Problem:** The `public` group is magically added in `resolve_token_groups()`.

**Solution:** Make behavior explicit and configurable.

**Implementation:**

```python
# Option A: Always include public in token at creation
def create_token(self, groups: List[str], ..., include_public: bool = True):
    if include_public and "public" not in groups:
        groups = ["public"] + groups
    # ... rest of creation

# Option B: Configuration flag on AuthService
class AuthService:
    def __init__(self, ..., implicit_public_group: bool = True):
        self._implicit_public = implicit_public_group
```

**Tests to Add (`tests/test_auth_phase4.py`):**

```python
class TestPublicGroupHandling:
    """Phase 4: Explicit public group behavior."""

    def test_public_included_by_default(self):
        """Public group is in token groups by default."""
        auth = create_memory_auth()
        token = auth.create_token(groups=["users"])
        info = auth.verify_token(token)
        
        assert "public" in info.groups
        assert "users" in info.groups

    def test_public_can_be_excluded(self):
        """Public group can be excluded from token."""
        auth = create_memory_auth()
        token = auth.create_token(groups=["users"], include_public=False)
        info = auth.verify_token(token)
        
        assert "public" not in info.groups
        assert "users" in info.groups

    def test_public_not_duplicated(self):
        """Public isn't added twice if already specified."""
        auth = create_memory_auth()
        token = auth.create_token(groups=["public", "users"])
        info = auth.verify_token(token)
        
        assert info.groups.count("public") == 1
```

**Acceptance Criteria:**
- [ ] `include_public` parameter added to `create_token()`
- [ ] `resolve_token_groups()` documents its behavior clearly
- [ ] All 3 tests pass

---

## 9. Implementation Priority Matrix

| Phase | Priority | Effort | Risk | Dependencies |
|-------|----------|--------|------|--------------|
| **1: Group Validation** | High | Low | Low | None |
| **2: File Caching** | Medium | Medium | Medium | None |
| **3: CLI Overhaul** | Medium | High | Low | None |
| **4: Public Group** | Low | Low | Medium | Phase 1 |

**Recommended Order:** Phase 1 → Phase 2 → Phase 4 → Phase 3

Phase 3 (CLI) has the highest effort and can be done in parallel or deferred, as it doesn't affect the core library.
