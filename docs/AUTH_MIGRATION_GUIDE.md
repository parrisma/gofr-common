# Auth System Migration Guide

This guide explains the new pluggable auth backend system and how to upgrade your code.

## Overview

The auth system now supports multiple storage backends:

| Backend | Use Case | Persistence | Shared State |
|---------|----------|-------------|--------------|
| **Memory** | Testing, development | None (process lifetime) | No |
| **File** | Single-instance deployments | JSON files | No |
| **Vault** | Production, multi-instance | HashiCorp Vault | Yes |

## Quick Start

### Minimal Setup (Memory Backend)

```python
from gofr_common.auth import (
    AuthService,
    GroupRegistry,
    MemoryTokenStore,
    MemoryGroupStore,
)

# Create stores
token_store = MemoryTokenStore()
group_store = MemoryGroupStore()

# Create registry and service
groups = GroupRegistry(store=group_store)
auth = AuthService(
    token_store=token_store,
    group_registry=groups,
    secret_key="your-secret-key",
)

# Use it
token = auth.create_token(groups=["admin"])
info = auth.verify_token(token)
```

### File Backend

```python
from gofr_common.auth import (
    AuthService,
    GroupRegistry,
    FileTokenStore,
    FileGroupStore,
)

# Create stores with paths
token_store = FileTokenStore(path="/data/tokens.json")
group_store = FileGroupStore(path="/data/groups.json")

# Create registry and service
groups = GroupRegistry(store=group_store)
auth = AuthService(
    token_store=token_store,
    group_registry=groups,
    secret_key="your-secret-key",
)
```

### Vault Backend (Production)

```python
from gofr_common.auth import (
    AuthService,
    GroupRegistry,
    VaultConfig,
    VaultClient,
    VaultTokenStore,
    VaultGroupStore,
)

# Configure Vault connection
config = VaultConfig(
    url="http://vault:8200",
    token="your-vault-token",  # Or use role_id/secret_id
)
client = VaultClient(config)

# Create stores
token_store = VaultTokenStore(client, path_prefix="myapp")
group_store = VaultGroupStore(client, path_prefix="myapp")

# Create registry and service
groups = GroupRegistry(store=group_store)
auth = AuthService(
    token_store=token_store,
    group_registry=groups,
    secret_key="your-secret-key",
)
```

### Using the Factory (Recommended)

The factory pattern simplifies backend selection via environment variables:

```python
from gofr_common.auth import create_stores_from_env, AuthService, GroupRegistry

# Reads GOFR_AUTH_BACKEND, GOFR_VAULT_URL, etc.
token_store, group_store = create_stores_from_env()

groups = GroupRegistry(store=group_store)
auth = AuthService(
    token_store=token_store,
    group_registry=groups,
    secret_key="your-secret-key",
)
```

**Environment Variables:**

| Variable | Description | Default |
|----------|-------------|---------|
| `GOFR_AUTH_BACKEND` | Backend type: `memory`, `file`, `vault` | `memory` |
| `GOFR_TOKEN_STORE_PATH` | File path for tokens (file backend) | `data/tokens.json` |
| `GOFR_GROUP_STORE_PATH` | File path for groups (file backend) | `data/groups.json` |
| `GOFR_VAULT_URL` | Vault server URL | `http://localhost:8200` |
| `GOFR_VAULT_TOKEN` | Vault token (dev mode) | - |
| `GOFR_VAULT_ROLE_ID` | Vault AppRole role ID | - |
| `GOFR_VAULT_SECRET_ID` | Vault AppRole secret ID | - |
| `GOFR_VAULT_MOUNT_POINT` | KV v2 mount point | `secret` |
| `GOFR_VAULT_PATH_PREFIX` | Path prefix in Vault | `gofr/auth` |

---

## Migration from Old API

### Before (Old API)

```python
# Old: Path-based initialization
from gofr_common.auth import AuthService, GroupRegistry

auth = AuthService(
    token_store_path="data/tokens.json",
    group_store_path="data/groups.json",
    secret_key="secret",
)

groups = GroupRegistry(store_path="data/groups.json")
```

### After (New API)

```python
# New: Explicit store injection
from gofr_common.auth import (
    AuthService,
    GroupRegistry,
    FileTokenStore,
    FileGroupStore,
)

token_store = FileTokenStore(path="data/tokens.json")
group_store = FileGroupStore(path="data/groups.json")

groups = GroupRegistry(store=group_store)
auth = AuthService(
    token_store=token_store,
    group_registry=groups,
    secret_key="secret",
)
```

### Key Changes

1. **No more path parameters** - Pass store instances instead
2. **GroupRegistry requires store** - No default in-memory fallback
3. **Explicit backend selection** - Choose your backend consciously
4. **Shared stores** - Pass same store to multiple components

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     AuthService                         │
│  - create_token()    - verify_token()                   │
│  - revoke_token()    - list_tokens()                    │
├─────────────────────────────────────────────────────────┤
│                    GroupRegistry                        │
│  - create_group()    - get_group()                      │
│  - make_defunct()    - list_groups()                    │
├─────────────────────────────────────────────────────────┤
│          TokenStore              │       GroupStore     │
│  (Protocol)                      │  (Protocol)          │
├──────────────────────────────────┼──────────────────────┤
│ MemoryTokenStore │ FileTokenStore│ MemoryGroupStore     │
│ VaultTokenStore  │               │ FileGroupStore       │
│                  │               │ VaultGroupStore      │
└──────────────────────────────────┴──────────────────────┘
```

### Protocols

Both `TokenStore` and `GroupStore` are Python Protocols (structural typing):

```python
class TokenStore(Protocol):
    def get(self, token_id: str) -> TokenRecord | None: ...
    def put(self, token_id: str, record: TokenRecord) -> None: ...
    def delete(self, token_id: str) -> None: ...
    def exists(self, token_id: str) -> bool: ...
    def list_all(self) -> dict[str, TokenRecord]: ...
    def clear(self) -> None: ...
    def __len__(self) -> int: ...

class GroupStore(Protocol):
    def get(self, group_id: str) -> Group | None: ...
    def put(self, group_id: str, group: Group) -> None: ...
    def delete(self, group_id: str) -> None: ...
    def exists(self, group_id: str) -> bool: ...
    def list_all(self) -> dict[str, Group]: ...
    def get_by_name(self, name: str) -> Group | None: ...
    def clear(self) -> None: ...
    def __len__(self) -> int: ...
```

You can implement custom backends by implementing these protocols.

---

## Vault Configuration

### Development Mode

For local development, run Vault in dev mode:

```bash
./docker/infra/vault/run.sh --test
```

This starts Vault with:
- URL: `http://localhost:8201` (host) / `http://gofr-vault:8200` (Docker)
- Token: `gofr-dev-root-token`
- KV v2 enabled at `secret/`

### Production Mode

For production, use AppRole authentication:

```python
config = VaultConfig(
    url="https://vault.example.com:8200",
    role_id="your-role-id",
    secret_id="your-secret-id",
    mount_point="secret",
    namespace="production",  # If using Vault Enterprise
    verify_ssl=True,
    timeout=30,
)
```

### Path Organization

Vault secrets are organized under the path prefix:

```
secret/
└── gofr/auth/           # Default path_prefix
    ├── tokens/
    │   ├── {token-id-1}
    │   └── {token-id-2}
    └── groups/
        ├── {group-id-1}
        ├── {group-id-2}
        └── _index       # Name-to-ID mapping
```

Use different `path_prefix` values to isolate environments:

```python
# Development
VaultTokenStore(client, path_prefix="dev/auth")

# Staging
VaultTokenStore(client, path_prefix="staging/auth")

# Production
VaultTokenStore(client, path_prefix="prod/auth")
```

---

## Testing

### Unit Tests (No Vault Required)

Use memory stores for fast, isolated unit tests:

```python
import pytest
from gofr_common.auth import (
    AuthService,
    GroupRegistry,
    MemoryTokenStore,
    MemoryGroupStore,
)

@pytest.fixture
def auth_service():
    token_store = MemoryTokenStore()
    group_store = MemoryGroupStore()
    groups = GroupRegistry(store=group_store)
    return AuthService(
        token_store=token_store,
        group_registry=groups,
        secret_key="test-secret",
    )

def test_create_token(auth_service):
    token = auth_service.create_token(groups=["admin"])
    info = auth_service.verify_token(token)
    assert info.groups == ["admin"]
```

### Integration Tests (Vault Required)

Mark tests that need Vault:

```python
import pytest

pytestmark = pytest.mark.vault_integration

def test_vault_token_store():
    # Test with real Vault
    ...
```

Run integration tests:

```bash
./scripts/run_tests.sh -m vault_integration
```

Skip integration tests (CI without Vault):

```bash
./scripts/run_tests.sh -m "not vault_integration"
```

---

## Common Patterns

### Singleton Pattern

For web applications, create stores once at startup:

```python
# app.py
from contextlib import asynccontextmanager
from gofr_common.auth import create_stores_from_env, AuthService, GroupRegistry

auth_service: AuthService = None

@asynccontextmanager
async def lifespan(app):
    global auth_service
    token_store, group_store = create_stores_from_env()
    groups = GroupRegistry(store=group_store)
    auth_service = AuthService(
        token_store=token_store,
        group_registry=groups,
        secret_key=settings.SECRET_KEY,
    )
    yield

app = Starlette(lifespan=lifespan)
```

### Dependency Injection

For FastAPI or similar:

```python
from functools import lru_cache

@lru_cache
def get_auth_service() -> AuthService:
    token_store, group_store = create_stores_from_env()
    groups = GroupRegistry(store=group_store)
    return AuthService(
        token_store=token_store,
        group_registry=groups,
        secret_key=settings.SECRET_KEY,
    )

@app.get("/protected")
def protected(auth: AuthService = Depends(get_auth_service)):
    ...
```

### Multi-Service Deployment

When multiple services share the same Vault:

```python
# Service A - Token issuer
auth_a = AuthService(
    token_store=VaultTokenStore(client, path_prefix="shared"),
    group_registry=GroupRegistry(store=VaultGroupStore(client, path_prefix="shared")),
    secret_key="shared-secret",  # Must match!
)

# Service B - Token verifier
auth_b = AuthService(
    token_store=VaultTokenStore(client, path_prefix="shared"),
    group_registry=GroupRegistry(
        store=VaultGroupStore(client, path_prefix="shared"),
        auto_bootstrap=False,  # Don't recreate reserved groups
    ),
    secret_key="shared-secret",  # Must match!
)

# Token created on A works on B
token = auth_a.create_token(groups=["admin"])
info = auth_b.verify_token(token)  # ✓ Works
```

---

## Troubleshooting

### "Vault unavailable" errors

1. Check Vault is running: `docker ps | grep vault`
2. Check connectivity: `curl http://localhost:8201/v1/sys/health`
3. Verify token: `VAULT_ADDR=http://localhost:8201 VAULT_TOKEN=gofr-dev-root-token vault token lookup`

### Token verification fails across services

- Ensure `secret_key` is identical across all services
- Ensure `path_prefix` is identical for shared state
- Check JWT expiration times

### Group not found after creation

- Vault has eventual consistency for list operations
- Use `get_group_by_name()` instead of listing then filtering

### Performance with Vault

- Vault stores are not cached - each operation hits Vault
- For high-throughput scenarios, consider caching verified tokens
- Use connection pooling (hvac handles this internally)

---

## API Reference

### AuthService

```python
class AuthService:
    def __init__(
        self,
        token_store: TokenStore,
        group_registry: GroupRegistry,
        secret_key: str,
        algorithm: str = "HS256",
        default_expiry_hours: int = 24,
    ): ...
    
    def create_token(
        self,
        groups: list[str],
        expires_in_hours: int | None = None,
    ) -> str: ...
    
    def verify_token(self, token: str) -> TokenInfo: ...
    def revoke_token(self, token: str) -> None: ...
    def list_tokens(self) -> list[TokenInfo]: ...
    def resolve_token_groups(self, token: str) -> list[Group]: ...
```

### GroupRegistry

```python
class GroupRegistry:
    def __init__(
        self,
        store: GroupStore,
        auto_bootstrap: bool = True,
    ): ...
    
    def create_group(
        self,
        name: str,
        description: str = "",
    ) -> Group: ...
    
    def get_group(self, group_id: UUID) -> Group | None: ...
    def get_group_by_name(self, name: str) -> Group | None: ...
    def make_defunct(self, group_id: UUID) -> None: ...
    def list_groups(self, include_defunct: bool = False) -> list[Group]: ...
```

### Factory Functions

```python
def create_token_store(
    backend: str = "memory",
    path: str | None = None,
    vault_client: VaultClient | None = None,
    vault_path_prefix: str = "gofr/auth",
) -> TokenStore: ...

def create_group_store(
    backend: str = "memory",
    path: str | None = None,
    vault_client: VaultClient | None = None,
    vault_path_prefix: str = "gofr/auth",
) -> GroupStore: ...

def create_stores_from_env() -> tuple[TokenStore, GroupStore]: ...
```
