# Auth Service Refactoring Plan

## Current Strengths ✅

1. **Clean Protocol-based Backend Abstraction** - `TokenStore` and `GroupStore` protocols allow swappable backends (memory, file, Vault)
2. **Reserved Groups** - `public` and `admin` are properly protected system groups
3. **Soft-delete Pattern** - Tokens and groups are never deleted, only marked defunct/revoked (good audit trail)
4. **JWT Best Practices** - Uses `jti`, `nbf`, `aud` claims properly
5. **Factory Pattern** - `create_stores_from_env()` provides clean configuration

---

## Issues & Recommendations

### 1. Global State in Middleware is an Anti-pattern 🔴 **HIGH PRIORITY**

**Status:** ✅ Completed

**Implementation:** Created `AuthProvider` class in `src/gofr_common/auth/provider.py` that provides dependency injection for FastAPI applications. The provider wraps an `AuthService` and exposes methods like `verify_token()`, `require_group()`, and `require_admin()` that return FastAPI dependencies.

**Problem:** `_auth_service` and `_security_auditor` are module-level globals, making testing harder and preventing multiple auth contexts.

```python
# Current (problematic)
_auth_service: Optional[AuthService] = None
def init_auth_service(...)
def get_auth_service() -> AuthService:
```

**Recommendation:** Use dependency injection via FastAPI's `Depends()`:

```python
# Proposed: AuthProvider class that can be injected
class AuthProvider:
    def __init__(self, auth_service: AuthService):
        self._service = auth_service
    
    @property
    def service(self) -> AuthService:
        return self._service
    
    def verify_token(self) -> Callable[..., TokenInfo]:
        """Returns a FastAPI dependency."""
        def _verify(request: Request, creds: HTTPAuthorizationCredentials = Security(security)) -> TokenInfo:
            return self._service.verify_token(creds.credentials, ...)
        return _verify
```

---

### 2. Dual Responsibility: AuthService does too much 🟡 **MEDIUM PRIORITY**

**Status:** ✅ Completed

**Implementation:** Created `TokenService` class in `src/gofr_common/auth/token_service.py` that handles pure JWT operations (create, verify, revoke, list). `AuthService` now uses `TokenService` internally via `self._token_service` and exposes it through the `tokens` property. This maintains backward compatibility while establishing clean separation of concerns.

**Problem:** `AuthService` handles both JWT operations AND orchestrates group registry. These are separate concerns.

**Current coupling:**
```python
class AuthService:
    def __init__(self, token_store, group_registry, ...):
        self._token_store = token_store
        self._group_registry = group_registry  # Why does JWT service own groups?
```

**Recommendation:** Split into focused services:

```python
# JWT-focused service
class TokenService:
    def __init__(self, store: TokenStore, secret_key: str, ...): ...
    def create(self, claims: Dict, groups: List[str], ...) -> str: ...
    def verify(self, token: str, ...) -> TokenInfo: ...
    def revoke(self, token: str) -> bool: ...

# Group validation is separate (or just use GroupRegistry directly)
class AuthService:
    """High-level orchestrator (if needed)"""
    def __init__(self, tokens: TokenService, groups: GroupRegistry): ...
```

---

### 3. `reload()` Called Too Frequently 🟡 **MEDIUM PRIORITY**

**Status:** ⬜ Not Started

**Problem:** `_reload_store()` is called on every `verify_token()`, `revoke_token()`, `list_tokens()`. For file/vault backends, this is inefficient.

```python
def verify_token(self, token: str, ...) -> TokenInfo:
    self._reload_store()  # Called EVERY verification!
```

**Recommendation:** 
- Make reload explicit (caller's choice) or use TTL-based caching
- For Vault backend, use Vault's read operations directly (no cache)
- For File backend, use file modification time check

---

### 4. Error Types are Inconsistent 🟡 **MEDIUM PRIORITY**

**Status:** ✅ Completed

**Implementation:** Created `src/gofr_common/auth/exceptions.py` with a consistent exception hierarchy:
- `AuthError` (401) - Base exception with HTTP status code
  - `TokenError` (401) - Token-related errors
    - `TokenNotFoundError`, `TokenRevokedError`, `TokenExpiredError`, `TokenValidationError`, `TokenServiceError`
  - `GroupError` (403) - Group access errors
    - `InvalidGroupError`, `GroupAccessDeniedError`
  - `AuthenticationError` (401)
    - `FingerprintMismatchError`

Middleware now catches `AuthError` and uses `error.status_code` for HTTP responses, eliminating the need for hardcoded status codes.

**Problem:** Mix of `ValueError`, custom exceptions, and HTTP exceptions across layers.

```python
# service.py uses ValueError
raise ValueError("Token has expired")

# But also has custom exceptions
class TokenRevokedError(Exception): ...

# middleware.py converts to HTTPException
raise HTTPException(status_code=401, detail=str(e))
```

**Recommendation:** Consistent exception hierarchy:

```python
class AuthError(Exception):
    """Base for all auth errors."""
    status_code: int = 401  # Default for HTTP conversion

class TokenExpiredError(AuthError): ...
class TokenRevokedError(AuthError): ...
class InvalidTokenError(AuthError): ...
class GroupAccessDenied(AuthError):
    status_code = 403

# Middleware just converts AuthError → HTTPException
```

---

### 5. Groups Are Validated at Token Creation but Not Verification 🟡 **MEDIUM PRIORITY**

**Status:** ⬜ Not Started

**Problem:** Token creation validates groups exist, but verification doesn't check if groups became defunct after token was issued.

```python
def create_token(self, groups: List[str], ...):
    for group_name in groups:
        group = self._group_registry.get_group_by_name(group_name)
        if not group.is_active:
            raise InvalidGroupError(...)  # ✅ Good

def verify_token(self, token: str, ...):
    # Groups from JWT are trusted, no check against registry! 🔴
```

**Recommendation:** Add optional group validation on verify:

```python
def verify_token(self, token: str, validate_groups: bool = False, ...) -> TokenInfo:
    ...
    if validate_groups:
        for group_name in groups:
            group = self._group_registry.get_group_by_name(group_name)
            if group is None or not group.is_active:
                raise InvalidGroupError(f"Group '{group_name}' no longer valid")
```

---

### 6. Fingerprinting is All-or-Nothing 🟢 **LOW PRIORITY**

**Status:** ⬜ Not Started

**Problem:** If a token has a fingerprint but the request doesn't provide one, verification passes. Should be configurable.

---

### 7. Simplification: Do You Need Groups in JWT? 🟡 **DISCUSSION**

**Status:** ⬜ Not Started

**Question:** Since you have a `TokenStore` that persists `TokenRecord` with groups, why also embed groups in the JWT payload?

**Current design:**
- JWT contains: `jti` (UUID), `groups`, `exp`, `iat`, `nbf`, `aud`
- Store contains: `TokenRecord(id, groups, status, ...)`

**Options:**
1. **Keep both** (current) - Good for stateless verification fallback
2. **JWT = reference only** - JWT only has `jti`, look up groups from store. Simpler JWT, always consistent with store.
3. **Stateless only** - No store, JWT is the source of truth. Simpler, but no revocation.

---

## Proposed Simplified Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      AuthService                             │
│  (High-level facade - optional, for convenience)             │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  TokenService   │  │  GroupRegistry  │  │  AuthProvider   │
│                 │  │                 │  │  (FastAPI DI)   │
│ - create()      │  │ - create()      │  │                 │
│ - verify()      │  │ - get_by_name() │  │ - verify_token  │
│ - revoke()      │  │ - make_defunct()│  │ - require_group │
└────────┬────────┘  └────────┬────────┘  └─────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌─────────────────┐
│   TokenStore    │  │   GroupStore    │
│   (Protocol)    │  │   (Protocol)    │
└─────────────────┘  └─────────────────┘
```

---

## Summary of Recommended Changes

| # | Priority | Issue | Recommendation | Status |
|---|----------|-------|----------------|--------|
| 1 | 🔴 High | Global state | Use dependency injection | ⬜ |
| 2 | 🟡 Medium | AuthService does too much | Split TokenService / GroupRegistry | ⬜ |
| 3 | 🟡 Medium | Excessive reload() | Make explicit or use caching | ⬜ |
| 4 | 🟡 Medium | Inconsistent errors | Create AuthError hierarchy | ⬜ |
| 5 | 🟡 Medium | Groups not validated on verify | Add `validate_groups` option | ⬜ |
| 6 | 🟢 Low | Fingerprinting all-or-nothing | Make configurable | ⬜ |
| 7 | 🟡 Discussion | JWT contains groups | Consider reference-only JWT | ⬜ |

---

## Implementation Notes

### Backward Compatibility

All changes should maintain backward compatibility with existing code. The global functions (`init_auth_service`, `get_auth_service`, etc.) can remain as convenience wrappers around the new `AuthProvider` class.

### Testing Strategy

Each refactoring should:
1. Maintain all existing tests passing
2. Add new tests for the refactored components
3. Test both the new DI approach and backward-compatible globals
