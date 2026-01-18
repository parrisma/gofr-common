#!/bin/bash
# =============================================================================
# Auth Manager Wrapper Script
# =============================================================================
# Wrapper for auth_manager.py that handles SSOT environment configuration.
#
# USAGE:
#   # From gofr-iq workspace (recommended - uses SSOT):
#   cd /path/to/gofr-iq
#   ./lib/gofr-common/scripts/auth_manager.sh --docker <command> [args...]
#
#   # Examples:
#   ./lib/gofr-common/scripts/auth_manager.sh --docker groups list
#   ./lib/gofr-common/scripts/auth_manager.sh --docker tokens create --groups admin --name dev-api
#   ./lib/gofr-common/scripts/auth_manager.sh --docker tokens list --format json
#   ./lib/gofr-common/scripts/auth_manager.sh --docker tokens revoke --name dev-api
#
# OPTIONS:
#   --docker          Use Docker hostnames (gofr-vault). Required in dev container.
#   --backend TYPE    Override backend (vault, file, memory). Default: vault
#   --help, -h        Show this help
#
# SSOT PATTERN:
#   This script automatically sources:
#   1. lib/gofr-common/config/gofr_ports.env  (ports)
#   2. docker/.vault-init.env                 (VAULT_TOKEN)
#   3. docker/.env                            (JWT_SECRET, NEO4J_PASSWORD, etc)
#
#   No manual environment setup needed!
#
# COMMANDS:
#   See: python lib/gofr-common/scripts/auth_manager.py --help
# =============================================================================

set -euo pipefail

# Default values
USE_DOCKER=false
BACKEND="vault"

# Parse wrapper flags (before passing to Python)
while [[ $# -gt 0 ]]; do
    case "$1" in
        --docker)
            USE_DOCKER=true
            shift
            ;;
        --backend)
            BACKEND="$2"
            shift 2
            ;;
        --help|-h)
            cat << 'EOF'
Auth Manager Wrapper - SSOT Environment Handler

USAGE:
  auth_manager.sh --docker <command> [args...]

OPTIONS:
  --docker          Use Docker hostnames (required in dev container)
  --backend TYPE    Backend type: vault (default), file, memory
  --help, -h        Show this help

EXAMPLES:
  # List groups:
  auth_manager.sh --docker groups list

  # Create admin token:
  auth_manager.sh --docker tokens create --groups admin --name dev-api

  # List tokens filtered by name pattern:
  auth_manager.sh --docker tokens list --name-pattern "prod-*"

  # Inspect token:
  auth_manager.sh --docker tokens inspect eyJhbGc...

  # Inspect by name:
  auth_manager.sh --docker tokens inspect --name dev-api

ENVIRONMENT (auto-sourced via SSOT):
  - lib/gofr-common/config/gofr_ports.env   (all ports)
  - docker/.vault-init.env                  (VAULT_TOKEN, VAULT_UNSEAL_KEY)
  - docker/.env                             (GOFR_JWT_SECRET, passwords, etc)

For full command reference, run:
  python lib/gofr-common/scripts/auth_manager.py --help
EOF
            exit 0
            ;;
        *)
            # First non-flag argument - pass everything to Python
            break
            ;;
    esac
done

# Find workspace root (where docker/ and lib/ exist)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_DIR="$(dirname "${SCRIPT_DIR}")"
WORKSPACE_ROOT="$(cd "${COMMON_DIR}/../.." && pwd)"

# Source SSOT files in correct order
PORTS_ENV="${COMMON_DIR}/config/gofr_ports.env"
VAULT_INIT="${WORKSPACE_ROOT}/docker/.vault-init.env"
DOCKER_ENV="${WORKSPACE_ROOT}/docker/.env"

if [[ ! -f "${PORTS_ENV}" ]]; then
    echo "ERROR: Port config not found: ${PORTS_ENV}" >&2
    echo "Run: ./scripts/generate_envs.sh" >&2
    exit 1
fi

if [[ ! -f "${DOCKER_ENV}" ]]; then
    echo "ERROR: Docker .env not found: ${DOCKER_ENV}" >&2
    echo "Run: ./docker/start-prod.sh --fresh" >&2
    exit 1
fi

# Source SSOT files
set -a
source "${PORTS_ENV}"
[[ -f "${VAULT_INIT}" ]] && source "${VAULT_INIT}"
source "${DOCKER_ENV}"
set +a

# Configure Vault URL based on --docker flag
if [[ "${USE_DOCKER}" == true ]]; then
    export GOFR_VAULT_URL="http://gofr-vault:${GOFR_VAULT_PORT}"
else
    export GOFR_VAULT_URL="http://localhost:${GOFR_VAULT_PORT}"
fi

# Set backend
export GOFR_AUTH_BACKEND="${BACKEND}"

# Ensure VAULT_TOKEN is set (prefer VAULT_ROOT_TOKEN from docker/.env)
export GOFR_VAULT_TOKEN="${VAULT_ROOT_TOKEN:-${VAULT_TOKEN:-}}"

# Display configuration
echo "=== Auth Manager Configuration ===" >&2
echo "Environment: prod" >&2
echo "Backend: ${BACKEND}" >&2
echo "Vault URL: ${GOFR_VAULT_URL}" >&2
echo "Vault Token: ${GOFR_VAULT_TOKEN}" >&2
echo "=====================================" >&2
echo "" >&2

# Run auth_manager.py with remaining arguments
cd "${SCRIPT_DIR}"
exec uv run python auth_manager.py --backend "${BACKEND}" "$@"
