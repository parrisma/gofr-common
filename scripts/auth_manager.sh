#!/bin/bash
# =============================================================================
# Auth Manager Wrapper Script
# =============================================================================
# Wrapper for auth_manager.py that handles SSOT environment configuration.
#
# RECOMMENDED USAGE:
#   # Simplest: use auth_env.sh to load secrets, then run this script
#   source <(./lib/gofr-common/scripts/auth_env.sh --docker)
#   ./lib/gofr-common/scripts/auth_manager.sh --docker groups list
#   ./lib/gofr-common/scripts/auth_manager.sh --docker tokens list
#
# LEGACY USAGE:
#   # From gofr-iq workspace (GOFR_JWT_SECRET required in env):
#   cd /path/to/gofr-iq
#   export GOFR_JWT_SECRET=$(vault kv get -field=value secret/gofr/config/jwt-signing-secret)
#   ./lib/gofr-common/scripts/auth_manager.sh --docker <command> [args...]
#
# SSOT PATTERN:
#   This script automatically sources:
#   1. lib/gofr-common/config/gofr_ports.env  (ports)
#   2. secrets/vault_root_token               (VAULT_TOKEN via Zero-Trust Bootstrap)
#   3. docker/.env                            (JWT_SECRET, NEO4J_PASSWORD, etc)
#
#   For the simplest flow, use auth_env.sh first:
#   source <(./lib/gofr-common/scripts/auth_env.sh --docker)
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
  # Recommended: use auth_env.sh first (one-liner)
  source <(./lib/gofr-common/scripts/auth_env.sh --docker) && \\
    ./lib/gofr-common/scripts/auth_manager.sh --docker groups list

  # List groups:
  ./lib/gofr-common/scripts/auth_manager.sh --docker groups list

  # List tokens:
  ./lib/gofr-common/scripts/auth_manager.sh --docker tokens list

  # Create admin token:
  ./lib/gofr-common/scripts/auth_manager.sh --docker tokens create --groups admin --name dev-api

  # List tokens filtered by name pattern:
  ./lib/gofr-common/scripts/auth_manager.sh --docker tokens list --name-pattern "prod-*"

  # Inspect token:
  ./lib/gofr-common/scripts/auth_manager.sh --docker tokens inspect eyJhbGc...

  # Inspect by name:
  ./lib/gofr-common/scripts/auth_manager.sh --docker tokens inspect --name dev-api

ENVIRONMENT:
  Recommended: source <(./lib/gofr-common/scripts/auth_env.sh --docker) first.
  This auto-loads:
    - VAULT_ADDR (with --docker, uses gofr-vault hostname)
    - VAULT_TOKEN (short-lived operator token, not root)
    - GOFR_JWT_SECRET (loaded from Vault)

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
SECRETS_DIR="${WORKSPACE_ROOT}/secrets"
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
source "${DOCKER_ENV}"
set +a

# Load Vault credentials from secrets/ directory (Zero-Trust Bootstrap)
if [[ -f "${SECRETS_DIR}/vault_root_token" ]]; then
    export VAULT_TOKEN=$(cat "${SECRETS_DIR}/vault_root_token")
fi

# Configure Vault URL based on --docker flag
if [[ "${USE_DOCKER}" == true ]]; then
    export GOFR_VAULT_URL="http://gofr-vault:${GOFR_VAULT_PORT}"
else
    export GOFR_VAULT_URL="http://localhost:${GOFR_VAULT_PORT}"
fi

# Set backend
export GOFR_AUTH_BACKEND="${BACKEND}"

# ZERO-TRUST BOOTSTRAP: VAULT_TOKEN must be explicitly loaded from secrets/ by caller
# No fallbacks - fail if not set
if [ -z "${VAULT_TOKEN:-}" ]; then
    echo "❌ ERROR: VAULT_TOKEN not set" >&2
    echo "   Load from: secrets/vault_root_token" >&2
    echo "   Example: export VAULT_TOKEN=\$(cat secrets/vault_root_token)" >&2
    exit 1
fi
export GOFR_VAULT_TOKEN="${VAULT_TOKEN}"

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
