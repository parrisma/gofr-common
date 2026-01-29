# GOFR Vault Architecture

## Overview

GOFR uses HashiCorp Vault as a centralized secrets manager and authentication backend. Vault is deployed once in `gofr-common` and consumed by all GOFR applications (gofr-iq, gofr-dig, gofr-plot, etc.).

**Read this first:**
- For auth flows and JWT storage rules, see [docs/auth/gofr_auth_system.md](lib/gofr-common/docs/auth/gofr_auth_system.md).
- Want the minimal steps? Skim [Bootstrap Process](#bootstrap-process-zero-trust) and [Runtime Token Flow](#runtime-token-flow).
- Troubleshooting? Jump to [Troubleshooting](#troubleshooting).

## Core Concepts

### What Vault Provides

| Capability | Description | GOFR Usage |
|------------|-------------|------------|
| **Secrets Storage** | Encrypted key-value store | JWT signing secrets, API keys, passwords |
| **Dynamic Secrets** | Short-lived credentials | Service AppRole tokens |
| **Auth Methods** | Identity verification | AppRole for services |
| **Access Policies** | Fine-grained permissions | Least-privilege service access |
| **Audit Logging** | Cryptographic audit trail | Security compliance |

### Key Terminology

| Term | Definition |
|------|------------|
| **Root Token** | God-mode access, used only for bootstrap/recovery |
| **Unseal Key** | Required to decrypt Vault data after restart |
| **AppRole** | Machine identity for service authentication |
| **Role ID** | Public identifier for an AppRole (like a username) |
| **Secret ID** | Private credential for an AppRole (like a password) |
| **Client Token** | Short-lived token issued after AppRole login |
| **KV v2** | Versioned key-value secrets engine |

## Architecture

```
┌─────────────────────────────────────────────┐
│ gofr-common (Shared Infrastructure)         │
│                                             │
│  ├── docker/                                │
│  │   ├── Dockerfile.vault                   │
│  │   ├── vault-compose.yml                  │
│  │   ├── vault-config.hcl                   │
│  │   └── entrypoint-vault.sh                │
│  │                                          │
│  ├── scripts/                               │
│  │   ├── manage_vault.sh                    │
│  │   └── bootstrap_vault.py                 │
│  │                                          │
│  └── secrets/                               │
│      ├── vault_root_token                   │
│      ├── vault_unseal_key                   │
│      └── bootstrap_tokens.json              │
└─────────────────────────────────────────────┘
              ▲
              │ Consumes (http://gofr-vault:8201)
              │
    ┌─────────┴──────────┬──────────────┐
    │                    │              │
┌───┴────┐        ┌──────┴───┐    ┌────┴─────┐
│gofr-iq │        │gofr-dig  │    │gofr-plot │
│(prod)  │        │(prod)    │    │(prod)    │
└────────┘        └──────────┘    └──────────┘

┌────────────────────────────────────────────┐
│ gofr-iq Tests (Isolated)                   │
│                                            │
│  docker-compose-test.yml                   │
│  ├── vault-test (ephemeral, port 8301)     │
│  ├── chromadb-test                         │
│  └── neo4j-test                            │
└────────────────────────────────────────────┘
```

## Production Mode

### Shared Vault Instance

**Location:** `lib/gofr-common/docker/vault-compose.yml`  
**Port:** `8201` (standard production port)  
**Container:** `gofr-vault`  
**Network:** `gofr-net` (shared Docker network)

### Lifecycle

1. **Start Vault** (one-time per machine):
   ```bash
   cd lib/gofr-common/scripts
   ./manage_vault.sh start
   ./manage_vault.sh unseal
   ```

2. **Bootstrap** (first run only):
   ```bash
   ./bootstrap_vault.py
   ```
   - Creates JWT auth backend
   - Sets JWT signing secret
   - Creates `admin` and `public` groups
   - Mints bootstrap tokens

3. **Start Application** (e.g., gofr-iq):
   ```bash
   cd docker
   ./start-prod.sh
   ```
   - Verifies Vault health at `http://gofr-vault:8201`
   - Creates/rotates service AppRoles (gofr-mcp, gofr-web, etc.)
   - Loads secrets from Vault
   - Starts application containers

### Key Characteristics

- **Persistent:** Data survives container restarts via Docker volumes
- **Sealed State:** Requires manual unseal after restart
- **Shared Secrets:** All applications use the same JWT signing secret
- **Zero Trust:** Services authenticate via AppRole, not root token
- **Health Gate:** Applications fail-fast if Vault is unavailable

## Test Mode

### Ephemeral Vault Instance

**Location:** `docker/docker-compose-test.yml` (per application)  
**Port:** `8301` (production + 100 offset)  
**Container:** `gofr-vault-test`  
**Mode:** `dev` (auto-unsealed, in-memory)

### Lifecycle

1. **Start Test Suite**:
   ```bash
   ./scripts/run_tests.sh
   ```
   - Starts ephemeral test infrastructure (vault-test, chromadb-test, neo4j-test)
   - Vault runs in dev mode (no seal/unseal required)
   - Bootstrap runs in pytest session fixture
   - Tests execute with isolated data
   - Cleanup: containers and volumes removed after tests

### Key Characteristics

- **Isolated:** Each application has its own test Vault
- **Ephemeral:** Data destroyed after test run
- **Dev Mode:** Auto-initialized, auto-unsealed, in-memory
- **Port Offset:** Test ports = production ports + 100
- **Independent:** No dependency on shared Vault

## Application Integration

### Environment Variables

**Production:**
```bash
GOFR_AUTH_BACKEND=vault
GOFR_VAULT_URL=http://gofr-vault:8201
GOFR_VAULT_TOKEN=${VAULT_ROOT_TOKEN}  # For setup only
# Services use AppRole credentials at runtime
```

**Test:**
```bash
GOFR_AUTH_BACKEND=vault
GOFR_VAULT_URL=http://gofr-vault-test:8200
GOFR_VAULT_TOKEN=gofr-dev-root-token  # Dev mode root token
```

### Service Authentication Flow

1. **Setup Phase** (start-prod.sh):
   - Uses root token to create/rotate AppRole
   - Saves credentials to `secrets/service_creds/gofr-{service}.json`

2. **Runtime Phase** (service containers):
   - Reads AppRole credentials from mounted secret file
   - Authenticates to Vault → receives short-lived token
   - Uses token to read secrets (JWT signing key, DB passwords, etc.)
   - Token auto-renews as needed

3. **Token Lifecycle**:
   - AppRole tokens: TTL = 1 hour, renewable
   - JWT tokens (for users): TTL = 24 hours, signed with secret from Vault

## Secrets Management

### Stored in Vault

| Path | Contents | Access |
|------|----------|--------|
| `secret/gofr/config/jwt-signing-secret` | JWT signing key | All services (read) |
| `secret/gofr/config/neo4j-password` | Neo4j database password | All services (read) |
| `secret/gofr/config/openrouter-api-key` | OpenRouter API key | MCP service (read) |
| `secret/gofr/auth/groups/{uuid}` | Group metadata | Auth services (CRUD) |
| `secret/gofr/auth/tokens/{uuid}` | Token metadata | Auth services (CRUD) |

### Stored on Disk (gofr-common/secrets/)

| File | Contents | Generated By |
|------|----------|--------------|
| `vault_root_token` | Root Vault access token | `VaultBootstrap.initialize()` |
| `vault_unseal_key` | Key to unseal Vault after restart | `VaultBootstrap.initialize()` |
| `bootstrap_tokens.json` | Admin and public JWT strings | `bootstrap.py` |
| `service_creds/gofr-mcp.json` | MCP service AppRole credentials | `setup_approle.py` |
| `service_creds/gofr-web.json` | Web service AppRole credentials | `setup_approle.py` |

**Security:**
- `secrets/` directory: `chmod 0700`
- Never committed to Git
- Symlinked from applications for compatibility

---

## Bootstrap Process (Zero-Trust)

The bootstrap process initializes Vault and creates all required secrets, groups, and tokens. It follows a zero-trust model where no secrets are hardcoded.

### Bootstrap Sequence Diagram

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  start-prod.sh  │     │   bootstrap.py  │     │     Vault       │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         │  1. Check Vault       │                       │
         │─────────────────────────────────────────────►│
         │                       │      HTTP 501        │
         │◄────────────────────────────────────────────│
         │  (Not Initialized)    │                       │
         │                       │                       │
         │  2. Initialize        │                       │
         │─────────────────────────────────────────────►│
         │                       │  root_token,         │
         │                       │  unseal_key          │
         │◄────────────────────────────────────────────│
         │                       │                       │
         │  3. Save to secrets/  │                       │
         │                       │                       │
         │  4. Unseal            │                       │
         │─────────────────────────────────────────────►│
         │                       │      HTTP 200        │
         │◄────────────────────────────────────────────│
         │                       │                       │
         │  5. Run bootstrap.py  │                       │
         │──────────────────────►│                       │
         │                       │  6. Store JWT secret │
         │                       │─────────────────────►│
         │                       │                       │
         │                       │  7. Create groups    │
         │                       │─────────────────────►│
         │                       │                       │
         │                       │  8. Create tokens    │
         │                       │─────────────────────►│
         │                       │                       │
         │                       │  9. Save tokens.json │
         │                       │                       │
         │  10. Setup AppRole    │                       │
         │─────────────────────────────────────────────►│
         │                       │                       │
         │  11. Start services   │                       │
         │                       │                       │
```

### Code Components

#### 1. VaultBootstrap Class (`gofr_common/vault/bootstrap.py`)

Handles low-level Vault initialization and unsealing:

```python
from gofr_common.vault import VaultBootstrap, VaultCredentials

bootstrap = VaultBootstrap(vault_addr="http://gofr-vault:8201")

# Check Vault state
if bootstrap.is_uninitialized():
    # First-time setup: initialize and save credentials
    creds: VaultCredentials = bootstrap.initialize()
    bootstrap.save_credentials(creds, secrets_dir=Path("secrets"))
    bootstrap.unseal(creds.unseal_key)

elif bootstrap.is_sealed():
    # After restart: load and unseal
    creds = bootstrap.load_credentials(secrets_dir=Path("secrets"))
    bootstrap.unseal(creds.unseal_key)
```

**Key Methods:**

| Method | Description |
|--------|-------------|
| `get_status()` | Returns HTTP code, initialized, sealed flags |
| `is_uninitialized()` | True if Vault needs first-time init |
| `is_sealed()` | True if Vault is sealed (needs unseal) |
| `is_healthy()` | True if Vault is ready for use |
| `initialize()` | Creates root token and unseal key |
| `unseal(key)` | Unseals Vault with the unseal key |
| `save_credentials(creds, path)` | Saves root token and unseal key to disk |
| `load_credentials(path)` | Loads saved credentials from disk |
| `auto_init_and_unseal(path)` | Complete bootstrap in one call |

#### 2. VaultAdmin Class (`gofr_common/auth/admin.py`)

Provides "God Mode" for configuring Vault auth methods:

```python
from gofr_common.auth.admin import VaultAdmin
from gofr_common.auth.backends.vault_client import VaultClient

client = VaultClient(config)
admin = VaultAdmin(client)

# Enable AppRole auth method
admin.enable_approle_auth()

# Create service policies
admin.update_policies()

# Create AppRole for a service
admin.provision_service_role("gofr-mcp", "gofr-mcp-policy")

# Generate credentials
creds = admin.generate_service_credentials("gofr-mcp")
# Returns: {"role_id": "...", "secret_id": "..."}
```

#### 3. VaultIdentity Class (`gofr_common/auth/identity.py`)

Runtime authentication for services using AppRole:

```python
from gofr_common.auth.identity import VaultIdentity

# Services read credentials from mounted secret
identity = VaultIdentity(creds_path="/run/secrets/vault_creds")
identity.login()           # Authenticate to Vault
identity.start_renewal()   # Background token renewal

# Get authenticated client for secret access
client = identity.get_client()
secret = client.read_secret("gofr/config/jwt-signing-secret")

# On shutdown
identity.stop()
```

**Key Features:**
- Loads role_id/secret_id from injected file
- Performs AppRole login to get client token
- Background thread auto-renews token before expiry
- Thread-safe and daemon-aware

### Secrets Created During Bootstrap

| Secret | Path in Vault | Created By |
|--------|---------------|------------|
| JWT Signing Secret | `secret/gofr/config/jwt-signing-secret` | `bootstrap.py` |
| `admin` Group | `secret/gofr/auth/groups/{uuid}` | `GroupRegistry.ensure_reserved_groups()` |
| `public` Group | `secret/gofr/auth/groups/{uuid}` | `GroupRegistry.ensure_reserved_groups()` |
| Admin Token | `secret/gofr/auth/tokens/{uuid}` | `AuthService.create_token()` |
| Public Token | `secret/gofr/auth/tokens/{uuid}` | `AuthService.create_token()` |

### Files Generated During Bootstrap

```
secrets/
├── vault_root_token           # Root access (emergency only)
├── vault_unseal_key           # Required after Vault restart
├── bootstrap_tokens.json      # {"admin_token": "eyJ...", "public_token": "eyJ..."}
└── service_creds/
    ├── gofr-mcp.json          # {"role_id": "...", "secret_id": "..."}
    └── gofr-web.json          # {"role_id": "...", "secret_id": "..."}
```

---

## Access Policies (Least Privilege)

Services only get access to the secrets they need. Policies are defined in `gofr_common/auth/policies.py`.

### Policy Structure

```hcl
# gofr-mcp-policy
# MCP Service - read own config + shared GOFR config

# Read MCP-specific secrets
path "secret/data/services/mcp/*" {
  capabilities = ["read"]
}

# Read GOFR shared config (JWT signing, etc)
path "secret/data/gofr/config/*" {
  capabilities = ["read"]
}

# Read/write GOFR auth data (groups, tokens)
path "secret/data/gofr/auth/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
```

### Service → Policy Mapping

| Service | Policy | Access |
|---------|--------|--------|
| gofr-mcp | `gofr-mcp-policy` | MCP secrets + GOFR config + Auth CRUD |
| gofr-web | `gofr-web-policy` | Web secrets + GOFR config + Auth CRUD |

---

## Runtime Token Flow

### How Services Authenticate at Runtime

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Service (MCP)  │     │     Vault       │     │  Secrets Store  │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         │  1. Read credentials  │                       │
         │  from /run/secrets/   │                       │
         │                       │                       │
         │  2. POST /auth/approle/login                  │
         │  {role_id, secret_id} │                       │
         │──────────────────────►│                       │
         │                       │                       │
         │  3. client_token      │                       │
         │  (TTL: 1 hour)        │                       │
         │◄──────────────────────│                       │
         │                       │                       │
         │  4. GET secret/data/gofr/config/jwt-signing-secret
         │  Authorization: client_token                  │
         │──────────────────────►│                       │
         │                       │  5. Read from KV     │
         │                       │─────────────────────►│
         │                       │◄────────────────────│
         │  6. {jwt_secret: ...} │                       │
         │◄──────────────────────│                       │
         │                       │                       │
         │  (Background: renew token before expiry)      │
         │                       │                       │
```

### Token Renewal

The `VaultIdentity` class handles automatic token renewal:

1. After login, records token TTL (e.g., 3600 seconds)
2. Background thread sleeps for `TTL * 0.75` (e.g., 45 minutes)
3. Calls `POST /auth/token/renew-self` to extend TTL
4. Repeats until `stop()` is called

This ensures services never experience token expiration during normal operation.

---

## Vault Integration with GOFR Auth System

The GOFR Auth System uses Vault as one of its pluggable storage backends. This section explains how they work together.

### Three Storage Backends

The Auth system supports three backends for storing token and group metadata:

| Backend | Use Case | Configuration |
|---------|----------|---------------|
| `memory` | Unit tests, ephemeral | `GOFR_AUTH_BACKEND=memory` |
| `file` | Development, single-node | `GOFR_AUTH_BACKEND=file` |
| `vault` | Production, distributed | `GOFR_AUTH_BACKEND=vault` |

### What Gets Stored Where

When using the Vault backend, the auth system stores **metadata only** - never JWT strings:

```
Vault (secret/gofr/auth/)
├── tokens/{jti-uuid}/
│   ├── name: "my-api-token"
│   ├── groups: ["us-sales", "reporting"]
│   ├── created_at: "2025-01-15T..."
│   ├── expires_at: "2026-01-15T..."
│   └── revoked: false
└── groups/{group-uuid}/
    ├── name: "us-sales"
    ├── description: "US Sales Team"
    └── is_defunct: false
```

**Important:** JWT strings are returned to the user at creation time and never stored. To revoke a token, we mark `revoked: true` in Vault, and validation checks this flag.

### VaultTokenStore and VaultGroupStore

The Vault backend is implemented in `gofr_common/auth/backends/vault.py`:

```python
from gofr_common.auth.backends.vault import VaultTokenStore, VaultGroupStore
from gofr_common.auth.backends.vault_client import VaultClient

# Initialize Vault client
client = VaultClient(config)

# Create stores
token_store = VaultTokenStore(client)
group_store = VaultGroupStore(client)

# Use via AuthService
auth_service = AuthService(token_store, group_store, jwt_secret)
```

### Token Validation Flow (Vault Backend)

When a JWT is validated:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  API Request    │     │   AuthService   │     │     Vault       │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         │  Authorization:       │                       │
         │  Bearer eyJ...        │                       │
         │──────────────────────►│                       │
         │                       │                       │
         │                       │  1. Decode JWT        │
         │                       │  Extract jti (UUID)   │
         │                       │                       │
         │                       │  2. GET secret/data/  │
         │                       │  gofr/auth/tokens/{jti}
         │                       │──────────────────────►│
         │                       │                       │
         │                       │  3. Token metadata    │
         │                       │◄──────────────────────│
         │                       │                       │
         │                       │  4. Check:            │
         │                       │  - revoked != true    │
         │                       │  - expires > now      │
         │                       │  - signature valid    │
         │                       │                       │
         │  200 OK / 401 Denied  │                       │
         │◄──────────────────────│                       │
```

### JWT Signing Secret Storage

The JWT signing secret is stored in Vault and retrieved at service startup:

```python
# During bootstrap
client.write_secret("gofr/config/jwt-signing-secret", {"value": generated_secret})

# At service startup
jwt_secret = client.read_secret("gofr/config/jwt-signing-secret")["value"]
auth_service = AuthService(..., jwt_secret=jwt_secret)
```

This ensures:
- All services use the same signing key
- Key rotation only requires Vault update + service restart
- Secret never appears in environment variables or config files

### Switching Backends

To switch from file to Vault backend (or vice versa):

1. Export existing data using auth_manager CLI
2. Update `GOFR_AUTH_BACKEND` environment variable
3. Import data to new backend
4. Restart services

See [GOFR Auth System Documentation](../auth/gofr_auth_system.md) for complete details on the auth system architecture.

---

## Port Allocation

**Source:** All port allocations are defined in `lib/gofr-common/config/gofr_ports.env`

Test ports follow the convention: **Production Port + 100**

| Service      | Production             | Test                        | Notes                |
|--------------|------------------------|-----------------------------|--------------------- |
| Vault        | `GOFR_VAULT_PORT=8201` | `GOFR_VAULT_PORT_TEST=8301` | Test uses dev mode   |
| gofr-iq MCP  | `GOFR_IQ_MCP_PORT=8080` | `GOFR_IQ_MCP_PORT_TEST=8180` | Model Context Proto  |
| gofr-iq MCPO | `GOFR_IQ_MCPO_PORT=8081` | `GOFR_IQ_MCPO_PORT_TEST=8181` | OpenAPI wrapper      |
| gofr-iq Web  | `GOFR_IQ_WEB_PORT=8082` | `GOFR_IQ_WEB_PORT_TEST=8182` | Health check         |
| ChromaDB     | `GOFR_CHROMA_PORT=8000` | `GOFR_CHROMA_PORT_TEST=8100` | Vector database      |
| Neo4j HTTP   | `GOFR_NEO4J_HTTP_PORT=7474` | `GOFR_NEO4J_HTTP_PORT_TEST=7574` | Graph database       |
| Neo4j Bolt   | `GOFR_NEO4J_BOLT_PORT=7687` | `GOFR_NEO4J_BOLT_PORT_TEST=7787` | Graph database       |
| OpenWebUI    | `GOFR_OPENWEBUI_PORT=8083` | `GOFR_OPENWEBUI_PORT_TEST=8183` | LLM Chat UI          |
| n8n          | `GOFR_N8N_PORT=8084` | `GOFR_N8N_PORT_TEST=8184` | Workflow automation  |

**Other GOFR applications** (gofr-doc, gofr-plot, gofr-np, gofr-dig) follow the same pattern with their own port ranges defined in `gofr_ports.env`.

## Common Operations

### Check Vault Status
```bash
cd lib/gofr-common/scripts
./manage_vault.sh status
```

### View Vault Logs
```bash
./manage_vault.sh logs
```

### Unseal Vault
```bash
./manage_vault.sh unseal
```

### Reinitialize (DESTRUCTIVE)
```bash
./manage_vault.sh stop
rm -rf ../data/vault/*
./manage_vault.sh start
./manage_vault.sh init  # Creates new unseal key + root token
./bootstrap_vault.py    # Recreate auth backend
```

### Rotate Service Credentials
```bash
cd gofr-iq
uv run scripts/setup_approle.py
```

## Troubleshooting

### "Vault not ready" Error

**Symptom:** `start-prod.sh` fails with "Vault not ready (HTTP 503)"

**Cause:** Vault is sealed or not running

**Fix:**
```bash
cd lib/gofr-common/scripts
./manage_vault.sh status  # Check if running
./manage_vault.sh unseal  # If sealed
```

### AppRole Authentication Failed

**Symptom:** Service fails to authenticate with "permission denied"

**Cause:** AppRole credentials missing or expired

**Fix:**
```bash
cd gofr-iq
uv run scripts/setup_approle.py  # Regenerate credentials
./scripts/start-prod.sh            # Restart services
```

### Test Failures with Vault Errors

**Symptom:** Tests fail with "connection refused" to Vault

**Cause:** Test Vault container not starting

**Fix:**
```bash
# Check test infrastructure
docker ps --filter name=vault-test

# View logs
docker logs gofr-vault-test

# Restart test suite
./scripts/run_tests.sh
```

## Migration from Embedded Vault

Applications that previously ran their own Vault instances should:

1. **Remove Vault service** from `docker-compose.yml`
2. **Update environment** to point to `gofr-vault:8201`
3. **Create symlink**: `ln -s lib/gofr-common/secrets secrets`
4. **Update start script** to check Vault health, not start it
5. **Keep test Vault** for test infrastructure independence

See [Vault Centralization Implementation Plan](vault_centralization_implementation_plan.md) for detailed migration steps.

## Security Considerations

### Production
- Vault sealed on restart (manual unseal required)
- Root token used only for setup, never at runtime
- Services use short-lived AppRole tokens
- Secrets never in environment variables (use Vault or mounted files)

### Development/Test
- Dev mode Vault auto-unseals (convenience over security)
- Ephemeral data (no persistence)
- Acceptable for test environments only

### Network Isolation
- Production Vault on `gofr-net` Docker network
- Only GOFR services can access Vault
- Firewall rules should restrict port 8201 to localhost

## References

- [Vault Official Docs](https://developer.hashicorp.com/vault/docs)
- [AppRole Auth Method](https://developer.hashicorp.com/vault/docs/auth/approle)
- [JWT/OIDC Auth Method](https://developer.hashicorp.com/vault/docs/auth/jwt)
- [Port Standardization](../config/port_standardization.md)
