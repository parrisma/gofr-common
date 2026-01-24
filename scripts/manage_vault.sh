#!/bin/bash
# Unified Vault lifecycle helper for the shared GOFR Vault
# Commands: start|stop|status|logs|init|unseal|env

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/vault-compose.yml"
SECRETS_DIR="${PROJECT_ROOT}/secrets"
DATA_DIR="${PROJECT_ROOT}/data/vault"
VAULT_ADDR_DEFAULT="http://localhost:8201"
CONTAINER_NAME="gofr-vault"

log() { echo "[vault-manage] $*"; }
err() { echo "[vault-manage][ERROR] $*" >&2; }

ensure_dirs() {
  mkdir -p "${SECRETS_DIR}" "${DATA_DIR}"
  chmod 700 "${SECRETS_DIR}" || true
}

start() {
  ensure_dirs
  log "Starting Vault via compose..."
  docker compose -f "${COMPOSE_FILE}" up -d
  log "Waiting for health..."
  sleep 3
  docker compose -f "${COMPOSE_FILE}" ps
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

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  logs) logs ;;
  init) start; init ;;
  unseal) unseal ;;
  env) env_cmd ;;
  *)
    echo "Usage: $0 {start|stop|status|logs|init|unseal|env}"
    exit 1
    ;;
esac
