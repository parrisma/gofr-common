# GOFR Vault Architecture

## Overview

GOFR uses HashiCorp Vault as a centralized secrets manager and authentication backend. Vault is deployed once in `gofr-common` and consumed by all GOFR applications (gofr-iq, gofr-dig, gofr-plot, etc.).

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

- JWT signing secret (`gofr/config/jwt-signing-secret`)
- Neo4j password (`gofr/config/neo4j-password`)
- OpenRouter API key (`gofr/config/openrouter-api-key`)
- Service AppRole credentials (via policy)

### Stored on Disk (gofr-common/secrets/)

- `vault_root_token` - Emergency access
- `vault_unseal_key` - Required after restart
- `bootstrap_tokens.json` - Admin and public bootstrap tokens
- `service_creds/` - AppRole credentials for each service

**Security:**
- `secrets/` directory: `chmod 0700`
- Never committed to Git
- Symlinked from applications for compatibility

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
./docker/start-prod.sh            # Restart services
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
