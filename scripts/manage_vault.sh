#!/bin/bash
# Unified Vault lifecycle helper for the shared GOFR Vault
# Commands: start|stop|status|logs|init|unseal|env|jwt-secret|bootstrap|health

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/vault-compose.yml"
SECRETS_DIR="${PROJECT_ROOT}/secrets"
DATA_DIR="${PROJECT_ROOT}/data/vault"
CONTAINER_NAME="gofr-vault"

# Auto-detect if running inside a container
if [ -f "/.dockerenv" ] || grep -qa "docker" /proc/1/cgroup 2>/dev/null; then
  VAULT_ADDR_DEFAULT="http://gofr-vault:8201"
else
  VAULT_ADDR_DEFAULT="http://localhost:8201"
fi

log() { echo "[vault-manage] $*"; }
err() { echo "[vault-manage][ERROR] $*" >&2; }

# Wait until Vault API is responsive and unsealed (or confirm sealed state).
# Returns 0 if unsealed, 1 if sealed, 2 if unreachable.
wait_vault_api_ready() {
  local max_attempts=${1:-15}
  local attempt=0
  while [ $attempt -lt $max_attempts ]; do
    attempt=$((attempt + 1))
    local status_json
    status_json=$(docker exec "${CONTAINER_NAME}" vault status -format=json 2>/dev/null) || true
    if [ -n "$status_json" ]; then
      local sealed
      sealed=$(echo "$status_json" | grep -o '"sealed": *[a-z]*' | sed 's/.*: *//')
      if [ "$sealed" = "false" ]; then
        return 0
      elif [ "$sealed" = "true" ]; then
        return 1
      fi
    fi
    sleep 2
  done
  return 2
}

# Check if Vault is sealed using JSON status (reliable, no text parsing races).
is_vault_sealed() {
  local status_json
  status_json=$(docker exec "${CONTAINER_NAME}" vault status -format=json 2>/dev/null) || true
  if [ -z "$status_json" ]; then
    return 0  # Can't reach = treat as sealed
  fi
  local sealed
  sealed=$(echo "$status_json" | grep -o '"sealed": *[a-z]*' | sed 's/.*: *//')
  [ "$sealed" = "true" ]
}

ensure_dirs() {
  mkdir -p "${SECRETS_DIR}" "${DATA_DIR}"
  chmod 700 "${SECRETS_DIR}" || true
}

ensure_volumes() {
  # Create Docker volumes if they don't exist
  for vol in gofr-vault-data gofr-vault-logs gofr-vault-file; do
    if ! docker volume inspect "$vol" >/dev/null 2>&1; then
      log "Creating volume: $vol"
      docker volume create "$vol" >/dev/null
    fi
  done
}

ensure_network() {
  # Create gofr-net network if it doesn't exist
  if ! docker network inspect gofr-net >/dev/null 2>&1; then
    log "Creating network: gofr-net"
    docker network create gofr-net >/dev/null
  fi
}

health_check() {
  log "=== Vault Health Check ==="
  
  # Check container is running
  if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    err "Container ${CONTAINER_NAME} is not running"
    return 1
  fi
  log "✓ Container is running"
  
  # Check vault is initialized
  local status_json
  status_json=$(docker exec "${CONTAINER_NAME}" vault status -format=json 2>/dev/null) || true
  if [ -z "$status_json" ]; then
    err "Cannot reach Vault API"
    return 1
  fi
  
  local initialized
  initialized=$(echo "$status_json" | grep -o '"initialized": *[a-z]*' | sed 's/.*: *//')
  if [ "$initialized" != "true" ]; then
    err "Vault is not initialized - run: $0 bootstrap"
    return 1
  fi
  log "✓ Vault is initialized"
  
  # Check vault is unsealed
  local sealed
  sealed=$(echo "$status_json" | grep -o '"sealed": *[a-z]*' | sed 's/.*: *//')
  if [ "$sealed" = "true" ]; then
    err "Vault is sealed - run: $0 unseal"
    return 1
  fi
  log "✓ Vault is unsealed"
  
  # Check secrets exist
  if [ ! -f "${SECRETS_DIR}/vault_root_token" ]; then
    err "Root token not found at ${SECRETS_DIR}/vault_root_token"
    return 1
  fi
  log "✓ Root token exists"
  
  if [ ! -f "${SECRETS_DIR}/vault_unseal_key" ]; then
    err "Unseal key not found at ${SECRETS_DIR}/vault_unseal_key"
    return 1
  fi
  log "✓ Unseal key exists"
  
  # Check KV secrets engine is enabled
  export VAULT_ADDR="${VAULT_ADDR_DEFAULT}"
  export VAULT_TOKEN=$(cat "${SECRETS_DIR}/vault_root_token")
  if ! docker exec -e VAULT_ADDR="http://127.0.0.1:8201" -e VAULT_TOKEN="${VAULT_TOKEN}" \
       "${CONTAINER_NAME}" vault secrets list 2>&1 | grep -q "^secret/"; then
    err "KV secrets engine not enabled at secret/"
    return 1
  fi
  log "✓ KV secrets engine enabled"
  
  # Check if auth is bootstrapped (check for a group)
  if ! docker exec -e VAULT_ADDR="http://127.0.0.1:8201" -e VAULT_TOKEN="${VAULT_TOKEN}" \
       "${CONTAINER_NAME}" vault kv list secret/gofr/auth/groups 2>/dev/null | grep -q .; then
    log "⚠ Auth not bootstrapped - run: $0 bootstrap"
    return 2  # Warning, not error
  fi
  log "✓ Auth is bootstrapped"
  
  log "=== All Health Checks Passed ==="
  return 0
}

start() {
  ensure_dirs
  ensure_volumes
  ensure_network
  log "Starting Vault via compose..."
  docker compose -f "${COMPOSE_FILE}" up -d
  log "Waiting for health..."
  sleep 3
  docker compose -f "${COMPOSE_FILE}" ps
  
  # Smart start: check if needs bootstrap
  if [ ! -f "${SECRETS_DIR}/vault_root_token" ]; then
    log "⚠ Vault needs initialization - run: $0 bootstrap"
  else
    # Wait for API to stabilize after start
    wait_vault_api_ready 10 || true
    if is_vault_sealed; then
      log "⚠ Vault is sealed - run: $0 unseal"
    else
      log "Vault is ready"
      # Run health check
      health_check || true
    fi
  fi
}

stop() {
  log "Stopping Vault..."
  docker compose -f "${COMPOSE_FILE}" down
}

status() {
  if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    err "Container ${CONTAINER_NAME} not running"
    exit 1
  fi
  docker exec "${CONTAINER_NAME}" vault status
}

logs() {
  docker logs -f "${CONTAINER_NAME}"
}

init() {
  ensure_dirs
  if [ -f "${SECRETS_DIR}/vault_root_token" ]; then
    err "vault_root_token already exists; skipping init"
    exit 1
  fi
  log "Initializing Vault (1 key, 1 threshold)..."
  docker exec "${CONTAINER_NAME}" vault operator init -key-shares=1 -key-threshold=1 \
    | tee "${SECRETS_DIR}/vault_init_output"
  UNSEAL_KEY=$(grep 'Unseal Key 1:' "${SECRETS_DIR}/vault_init_output" | awk '{print $4}')
  ROOT_TOKEN=$(grep 'Initial Root Token:' "${SECRETS_DIR}/vault_init_output" | awk '{print $4}')
  echo -n "${UNSEAL_KEY}" > "${SECRETS_DIR}/vault_unseal_key"
  echo -n "${ROOT_TOKEN}" > "${SECRETS_DIR}/vault_root_token"
  chmod 600 "${SECRETS_DIR}/vault_unseal_key" "${SECRETS_DIR}/vault_root_token"
  log "Init complete; credentials saved in ${SECRETS_DIR}"
  
  # Unseal vault automatically
  log "Unsealing Vault..."
  docker exec "${CONTAINER_NAME}" vault operator unseal "${UNSEAL_KEY}" > /dev/null
  
  # Enable KV v2 secrets engine
  log "Enabling KV v2 secrets engine at secret/..."
  docker exec -e VAULT_TOKEN="${ROOT_TOKEN}" "${CONTAINER_NAME}" vault secrets enable -path=secret kv-v2 || {
    log "KV secrets engine already enabled or error occurred"
  }
  
  # Enable AppRole auth method
  log "Enabling AppRole auth method..."
  docker exec -e VAULT_TOKEN="${ROOT_TOKEN}" "${CONTAINER_NAME}" vault auth enable approle || {
    log "AppRole auth already enabled or error occurred"
  }
}

unseal() {
  if [ ! -f "${SECRETS_DIR}/vault_unseal_key" ]; then
    err "vault_unseal_key missing; run init first"
    exit 1
  fi
  KEY=$(cat "${SECRETS_DIR}/vault_unseal_key")
  log "Unsealing Vault..."
  docker exec "${CONTAINER_NAME}" vault operator unseal "${KEY}"
}

env_cmd() {
  VAULT_TOKEN_FILE="${SECRETS_DIR}/vault_root_token"
  if [ -f "${VAULT_TOKEN_FILE}" ]; then
    export VAULT_TOKEN=$(cat "${VAULT_TOKEN_FILE}")
  fi
  export VAULT_ADDR="${VAULT_ADDR_DEFAULT}"
  echo "export VAULT_ADDR=${VAULT_ADDR}"
  [ -n "${VAULT_TOKEN:-}" ] && echo "export VAULT_TOKEN=${VAULT_TOKEN}"
}

ensure_jwt_secret() {
  # Idempotent: create JWT signing secret in Vault if it doesn't exist
  log "Ensuring JWT signing secret exists..."
  
  if [ ! -f "${SECRETS_DIR}/vault_root_token" ]; then
    err "vault_root_token not found - run init first"
    return 1
  fi
  
  local VAULT_TOKEN=$(cat "${SECRETS_DIR}/vault_root_token")
  local JWT_PATH="secret/gofr/config/jwt-signing-secret"
  
  # Check if secret already exists
  if docker exec -e VAULT_ADDR="http://127.0.0.1:8201" -e VAULT_TOKEN="${VAULT_TOKEN}" \
       "${CONTAINER_NAME}" vault kv get -field=value "${JWT_PATH}" >/dev/null 2>&1; then
    log "✓ JWT signing secret already exists"
    return 0
  fi
  
  # Generate and store new secret
  log "Creating JWT signing secret..."
  local JWT_SECRET=$(openssl rand -hex 32)
  if ! docker exec -e VAULT_ADDR="http://127.0.0.1:8201" -e VAULT_TOKEN="${VAULT_TOKEN}" \
       "${CONTAINER_NAME}" vault kv put "${JWT_PATH}" value="${JWT_SECRET}" >/dev/null 2>&1; then
    err "Failed to write JWT signing secret to Vault"
    return 1
  fi
  log "✓ JWT signing secret created at ${JWT_PATH}"
}

bootstrap() {
  log "=== Full Vault Bootstrap ==="
  
  # Build image if needed
  if ! docker images | grep -q "gofr-vault.*latest"; then
    log "Building Vault image..."
    cd "${PROJECT_ROOT}"
    docker build -f docker/Dockerfile.vault -t gofr-vault:latest .
  else
    log "Vault image exists"
  fi
  
  # Initialize if needed (this also starts and unseals)
  if [ ! -f "${SECRETS_DIR}/vault_root_token" ]; then
    log "Initializing vault for first time..."
    start
    log "Waiting for Vault API to become reachable..."
    if ! wait_vault_api_ready 20; then
      err "Vault API did not become reachable after start"
      return 1
    fi
    init
  else
    log "Vault already initialized"
    # Ensure it's running
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
      start
    fi
    # Wait for Vault API to be reachable after (re)start
    log "Waiting for Vault API to stabilize..."
    wait_vault_api_ready 15 || true
    # Always check if sealed and unseal if needed (using reliable JSON check)
    if is_vault_sealed; then
      log "Vault is sealed — unsealing..."
      unseal
      sleep 2
      # Verify unseal succeeded
      if is_vault_sealed; then
        err "Vault is still sealed after unseal attempt"
        return 1
      fi
    else
      log "Vault is already unsealed"
    fi
  fi

  # Verify Vault API is truly ready before configuring
  log "Confirming Vault API is ready..."
  if ! wait_vault_api_ready 10; then
    err "Vault API not ready — cannot continue with bootstrap"
    return 1
  fi
  log "✓ Vault API is responsive and unsealed"

  # Ensure KV v2 secrets engine is enabled
  local VAULT_TOKEN_VAL
  VAULT_TOKEN_VAL=$(cat "${SECRETS_DIR}/vault_root_token")
  if ! docker exec -e VAULT_ADDR="http://127.0.0.1:8201" -e VAULT_TOKEN="${VAULT_TOKEN_VAL}" \
       "${CONTAINER_NAME}" vault secrets list 2>/dev/null | grep -q "^secret/"; then
    log "Enabling KV v2 secrets engine at secret/..."
    docker exec -e VAULT_ADDR="http://127.0.0.1:8201" -e VAULT_TOKEN="${VAULT_TOKEN_VAL}" \
      "${CONTAINER_NAME}" vault secrets enable -path=secret kv-v2 || {
      err "Failed to enable KV secrets engine"
      return 1
    }
  fi
  log "✓ KV v2 secrets engine enabled"

  # Ensure AppRole auth method is enabled
  if ! docker exec -e VAULT_ADDR="http://127.0.0.1:8201" -e VAULT_TOKEN="${VAULT_TOKEN_VAL}" \
       "${CONTAINER_NAME}" vault auth list 2>/dev/null | grep -q "approle/"; then
    log "Enabling AppRole auth method..."
    docker exec -e VAULT_ADDR="http://127.0.0.1:8201" -e VAULT_TOKEN="${VAULT_TOKEN_VAL}" \
      "${CONTAINER_NAME}" vault auth enable approle || {
      err "Failed to enable AppRole auth"
      return 1
    }
  fi
  log "✓ AppRole auth method enabled"

  # Ensure JWT signing secret exists (idempotent)
  ensure_jwt_secret || {
    err "Failed to ensure JWT signing secret — is Vault unsealed?"
    return 1
  }
  
  # Run auth bootstrap
  log "Bootstrapping authentication (JWT, groups, tokens)..."
  export VAULT_ADDR="${VAULT_ADDR_DEFAULT}"
  export VAULT_TOKEN=$(cat "${SECRETS_DIR}/vault_root_token")
  cd "${PROJECT_ROOT}"
  
  # Check if Python script exists
  if [ -f "${PROJECT_ROOT}/scripts/bootstrap_vault.py" ]; then
    # Try uv first, fallback to python3
    if command -v uv >/dev/null 2>&1; then
      uv run scripts/bootstrap_vault.py
    else
      python3 scripts/bootstrap_vault.py
    fi
  else
    err "bootstrap_vault.py not found at ${PROJECT_ROOT}/scripts/bootstrap_vault.py"
    exit 1
  fi
  
  log "=== Bootstrap Complete ==="
  log "Secrets saved to: ${SECRETS_DIR}"
  log "  - vault_root_token"
  log "  - vault_unseal_key"
  log "  - bootstrap_tokens.json"
  log ""
  log "To use Vault, run:"
  log "  source <(${SCRIPT_DIR}/manage_vault.sh env)"
  log ""
  
  # Run final health check
  health_check
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  logs) logs ;;
  init) start; init ;;
  unseal) unseal ;;
  env) env_cmd ;;
  jwt-secret) ensure_jwt_secret ;;
  bootstrap) bootstrap ;;
  health) health_check ;;
  *)
    echo "Usage: $0 {start|stop|status|logs|init|unseal|env|jwt-secret|bootstrap|health}"
    exit 1
    ;;
esac
