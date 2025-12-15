# Auth Service Refactoring Specification

## Requirements

1. **Central Register of Groups**
   - 1.1 Groups can be created and made defunct but NEVER deleted
   - 1.2 A group has a string name, an optional description, and a GUID
   - 1.3 Reserved groups (`public`, `admin`) always exist and cannot be made defunct

2. **Central Register of Access Tokens**
   - 2.1 Tokens can be created and revoked but never deleted
   - 2.2 A token has an optional expiry at which point it becomes revoked
   - 2.3 A token points to a list of one or more groups
   - 2.4 A group can be pointed at by zero or more tokens
   - 2.5 Tokens are signed to prove authenticity

3. **Token Validation**
   - Tokens can be validated by signature and then resolved into the associated list of groups
   - The `public` group is always included in resolved groups for any valid token

4. **Reserved Groups**
   - `public`: Automatically added to every token's resolved groups. Cannot be defunct.
   - `admin`: Required for group/token management operations. Cannot be defunct.
   - Reserved groups are bootstrapped via init script (direct store access)

5. **Authorization**
   - Creating/modifying groups requires `admin` group membership
   - Creating/revoking tokens requires `admin` group membership
   - Resolving tokens does NOT require admin (read-only operation)

---

## Phased Implementation Plan

### Phase 1: Create Group Model and Registry

**Goal:** Introduce the `Group` model and `GroupRegistry` with reserved groups support.

#### Step 1.1: Create Group Model
- [ ] Add `Group` dataclass with: `id` (UUID), `name` (str), `description` (Optional[str]), `is_active` (bool), `created_at`, `defunct_at` (Optional), `is_reserved` (bool)
- [ ] Add `to_dict()` and `from_dict()` for serialization
- [ ] Add tests for `Group` creation and serialization
- [ ] Run tests: `./scripts/run_tests.sh -k "test_group"`

#### Step 1.2: Create GroupRegistry Class
- [ ] Add `GroupRegistry` class with in-memory and file-based storage
- [ ] Define `RESERVED_GROUPS = {"public", "admin"}`
- [ ] Implement `create_group(name, description=None) -> Group` (reject reserved names)
- [ ] Implement `get_group(group_id: UUID) -> Optional[Group]`
- [ ] Implement `get_group_by_name(name: str) -> Optional[Group]`
- [ ] Implement `list_groups(include_defunct=False) -> List[Group]`
- [ ] Implement `make_defunct(group_id: UUID) -> bool` (reject reserved groups)
- [ ] Add `ensure_reserved_groups()` method for bootstrap
- [ ] Add tests for all GroupRegistry methods including reserved group protection
- [ ] Run tests: `./scripts/run_tests.sh -k "test_group"`

#### Step 1.3: Create Bootstrap Script
- [ ] Create `scripts/init_auth.py` for bootstrapping
- [ ] Script creates `public` and `admin` groups directly in store
- [ ] Script creates initial admin token with `admin` group
- [ ] Script outputs admin token to stdout/file for initial setup
- [ ] Add documentation for bootstrap process
- [ ] Run tests: `./scripts/run_tests.sh -k "test_bootstrap"`

---

### Phase 2: Create New Token Models

**Goal:** Define new token data structures.

#### Step 2.1: Create TokenRecord Model
- [ ] Add `TokenRecord` dataclass with:
  - `id` (UUID) - unique token identifier
  - `groups` (List[str]) - list of group names
  - `status` (Literal["active", "revoked"]) 
  - `created_at` (datetime)
  - `expires_at` (Optional[datetime])
  - `revoked_at` (Optional[datetime])
  - `fingerprint` (Optional[str])
- [ ] Add `to_dict()` and `from_dict()` for serialization
- [ ] Add `is_expired` property
- [ ] Add `is_valid` property (active and not expired)
- [ ] Add tests for TokenRecord
- [ ] Run tests: `./scripts/run_tests.sh -k "test_token_record"`

#### Step 2.2: Update TokenInfo
- [ ] Change `TokenInfo` to have `groups: List[str]` instead of `group: str`
- [ ] Update all fields to match new structure
- [ ] Update existing tests
- [ ] Run tests: `./scripts/run_tests.sh -k "test_token_info"`

---

### Phase 3: Rewrite AuthService

**Goal:** Replace AuthService internals with new architecture.

#### Step 3.1: Update Token Store Structure
- [ ] Change token store to be keyed by UUID string (not JWT)
- [ ] Store `TokenRecord` data in store
- [ ] Update `_load_token_store()` and `_save_token_store()`
- [ ] Add tests for new store format
- [ ] Run tests: `./scripts/run_tests.sh -k "test_auth"`

#### Step 3.2: Integrate GroupRegistry
- [ ] Add `GroupRegistry` as required component of `AuthService`
- [ ] Share storage path logic between token store and group registry
- [ ] Add `auth.groups` property to access registry
- [ ] Call `ensure_reserved_groups()` on init (creates if missing)
- [ ] Add tests for integrated service
- [ ] Run tests: `./scripts/run_tests.sh`

#### Step 3.3: Rewrite create_token
- [ ] Change signature to `create_token(groups: List[str], ...)`
- [ ] Validate all groups exist in registry and are active
- [ ] Auto-generate UUID for token
- [ ] Store `TokenRecord` in store (keyed by UUID)
- [ ] Return signed JWT containing UUID and groups
- [ ] **Note:** Admin check enforced at middleware level, not here
- [ ] Update tests
- [ ] Run tests: `./scripts/run_tests.sh -k "test_create"`

#### Step 3.4: Rewrite verify_token
- [ ] Decode JWT and extract UUID
- [ ] Look up `TokenRecord` by UUID
- [ ] Check status is "active"
- [ ] Check not expired
- [ ] Return `TokenInfo` with groups list
- [ ] Update tests
- [ ] Run tests: `./scripts/run_tests.sh -k "test_verify"`

#### Step 3.5: Rewrite revoke_token
- [ ] Accept token JWT string
- [ ] Extract UUID from JWT
- [ ] Set `TokenRecord.status = "revoked"` and `revoked_at = now`
- [ ] Do NOT delete from store
- [ ] **Note:** Admin check enforced at middleware level, not here
- [ ] Update tests
- [ ] Run tests: `./scripts/run_tests.sh -k "test_revoke"`

#### Step 3.6: Update list_tokens
- [ ] Return all `TokenRecord` entries with full metadata
- [ ] Add optional `status` filter parameter
- [ ] Update tests
- [ ] Run tests: `./scripts/run_tests.sh -k "test_list"`

---

### Phase 4: Add Group Resolution

**Goal:** Add method to resolve token to Group objects with `public` auto-inclusion.

#### Step 4.1: Add resolve_token_groups
- [ ] Add `resolve_token_groups(token: str, include_defunct=False) -> List[Group]`
- [ ] Verify token, get group names from TokenInfo
- [ ] Look up each group in registry
- [ ] **Always include `public` group in result** (even if not in token)
- [ ] Return list of Group objects
- [ ] Add tests (verify public always present)
- [ ] Run tests: `./scripts/run_tests.sh -k "test_resolve"`

#### Step 4.2: Remove get_group_for_token
- [ ] Delete `get_group_for_token()` method
- [ ] Update any internal usages
- [ ] Remove old tests
- [ ] Run tests: `./scripts/run_tests.sh`

---

### Phase 5: Update Middleware

**Goal:** Update FastAPI middleware for multi-group tokens with admin enforcement.

#### Step 5.1: Update verify_token Dependency
- [ ] Update to return `TokenInfo` with `groups: List[str]`
- [ ] Set `request.state.groups` (list)
- [ ] Update tests
- [ ] Run tests: `./scripts/run_tests.sh -k "test_middleware"`

#### Step 5.2: Add Authorization Helpers
- [ ] Add `require_group(group_name: str)` dependency
- [ ] Add `require_any_group(group_names: List[str])` dependency  
- [ ] Add `require_all_groups(group_names: List[str])` dependency
- [ ] Add `require_admin()` dependency (convenience for `require_group("admin")`)
- [ ] Add tests
- [ ] Run tests: `./scripts/run_tests.sh`

---

### Phase 6: Update Exports and Documentation

**Goal:** Clean up public API.

#### Step 6.1: Update __init__.py
- [ ] Export `Group`, `GroupRegistry`, `TokenRecord`
- [ ] Export `RESERVED_GROUPS` constant
- [ ] Export authorization helpers including `require_admin`
- [ ] Update module docstring

#### Step 6.2: Update All Docstrings
- [ ] Update `AuthService` class docstring
- [ ] Update all public method docstrings
- [ ] Add usage examples
- [ ] Document reserved groups behavior

#### Step 6.3: Final Test Run
- [ ] Run full test suite: `./scripts/run_tests.sh`
- [ ] Verify all tests pass

---

## Data Models (Final)

### Group
```python
@dataclass
class Group:
    id: UUID
    name: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    defunct_at: Optional[datetime]
    is_reserved: bool  # True for public, admin
```

### TokenRecord
```python
@dataclass  
class TokenRecord:
    id: UUID
    groups: List[str]
    status: Literal["active", "revoked"]
    created_at: datetime
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    fingerprint: Optional[str]
```

### TokenInfo (returned from verify)
```python
@dataclass
class TokenInfo:
    token: str
    groups: List[str]
    expires_at: Optional[datetime]
    issued_at: datetime
```

---

## Reserved Groups

### Constants
```python
RESERVED_GROUPS = frozenset({"public", "admin"})
```

### Behavior

| Group | Purpose | Auto-included | Can be Defunct |
|-------|---------|---------------|----------------|
| `public` | Universal access | Yes (on resolution) | No |
| `admin` | Management operations | No | No |

### Bootstrap Process
The init script (`scripts/init_auth.py`) performs:
1. Creates `groups.json` with `public` and `admin` groups (if not exists)
2. Creates `tokens.json` with initial admin token (if not exists)
3. Outputs admin JWT to stdout for initial system access

```bash
# First-time setup
python scripts/init_auth.py --data-dir /path/to/data/auth
# Output: Admin token: eyJhbG...
```

---

## Storage Format (Final)

### groups.json
```json
{
  "550e8400-e29b-41d4-a716-446655440000": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "public",
    "description": "Universal access group - automatically included for all tokens",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00",
    "defunct_at": null,
    "is_reserved": true
  },
  "550e8400-e29b-41d4-a716-446655440001": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "admin",
    "description": "Administrative access - required for group and token management",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00",
    "defunct_at": null,
    "is_reserved": true
  },
  "uuid-3": {
    "id": "uuid-3",
    "name": "users",
    "description": "Regular users",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00",
    "defunct_at": null,
    "is_reserved": false
  }
}
```

### tokens.json
```json
{
  "uuid-1": {
    "id": "uuid-1", 
    "groups": ["admin"],
    "status": "active",
    "created_at": "2024-01-01T00:00:00",
    "expires_at": null,
    "revoked_at": null,
    "fingerprint": null
  }
}
```

---

## Authorization Matrix

| Operation | Required Group |
|-----------|---------------|
| `create_group()` | admin |
| `make_defunct()` | admin |
| `create_token()` | admin |
| `revoke_token()` | admin |
| `list_groups()` | (any valid token) |
| `list_tokens()` | admin |
| `verify_token()` | (no token required) |
| `resolve_token_groups()` | (any valid token) |
