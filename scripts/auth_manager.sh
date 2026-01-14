#!/bin/bash
# =============================================================================
# Auth Manager Wrapper Script
# =============================================================================
# Wrapper for auth_manager.py that handles environment configuration.
#
# Usage:
#   ./auth_manager.sh [--env prod|dev] [--docker] <command> [args...]
#
# Options:
#   --env prod|dev    Environment mode (default: prod)
#                     - prod: Use production ports from gofr_ports.env
#                     - dev: Use test ports (prod + 100)
#   --docker          Use Docker container hostnames (default: localhost)
#
# Examples:
#   ./auth_manager.sh groups list
#   ./auth_manager.sh --env dev groups list
#   ./auth_manager.sh --docker tokens list
#   ./auth_manager.sh --env dev --docker groups create --name mygroup
# =============================================================================

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_DIR="$(dirname "${SCRIPT_DIR}")"
CONFIG_DIR="${COMMON_DIR}/config"

# Default values
ENV_MODE="prod"
USE_DOCKER=false
BACKEND="vault"

# Parse flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env)
            ENV_MODE="$2"
            shift 2
            ;;
        --docker)
            USE_DOCKER=true
            shift
            ;;
        --backend)
            BACKEND="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--env prod|dev] [--docker] [--backend vault|file|memory] <command> [args...]"
            echo ""
            echo "Options:"
            echo "  --env prod|dev    Environment mode (default: prod)"
            echo "  --docker          Use Docker container hostnames (default: localhost)"
            echo "  --backend         Auth backend (default: vault)"
            echo ""
            echo "Commands:"
            echo "  groups list                          List all groups"
            echo "  groups create --name NAME            Create a group"
            echo "  groups delete --name NAME            Delete a group"
            echo "  tokens list                          List all tokens"
            echo "  tokens create --name NAME --groups G1,G2  Create a token"
            echo "  tokens delete --name NAME            Delete a token"
            echo ""
            exit 0
            ;;
        *)
            # First non-flag argument starts the command
            break
            ;;
    esac
done

# Validate environment mode
if [[ "${ENV_MODE}" != "prod" && "${ENV_MODE}" != "dev" ]]; then
    echo "Error: --env must be 'prod' or 'dev'" >&2
    exit 1
fi

# Source port configuration (.env)
PORTS_ENV="${CONFIG_DIR}/gofr_ports.env"
if [[ ! -f "${PORTS_ENV}" ]]; then
    echo "Error: Port configuration not found at ${PORTS_ENV}" >&2
    exit 1
fi

set -a
source "${PORTS_ENV}"

# Source main .env file for tokens
MAIN_ENV="${COMMON_DIR}/.env"
if [[ -f "${MAIN_ENV}" ]]; then
    source "${MAIN_ENV}"
fi
set +a

# Set test ports if dev mode
if [[ "${ENV_MODE}" == "dev" ]]; then
    export GOFR_VAULT_PORT="${GOFR_VAULT_PORT_TEST:-${GOFR_VAULT_PORT}}"
fi

# Set hostname based on docker flag - NO localhost fallback for production
if [[ "${USE_DOCKER}" == true ]]; then
    VAULT_HOST="gofr-vault"
else
    # Running outside docker - require explicit GOFR_VAULT_URL
    echo "ERROR: Must use --docker flag when running in container environment" >&2
    echo "       Or set GOFR_VAULT_URL explicitly for localhost access" >&2
    exit 1
fi

# Configure Vault environment variables
export GOFR_AUTH_BACKEND="${BACKEND}"
export GOFR_VAULT_URL="http://${VAULT_HOST}:${GOFR_VAULT_PORT}"
# Use GOFR_VAULT_TOKEN if set, otherwise fall back to dev token
export GOFR_VAULT_TOKEN="${GOFR_VAULT_TOKEN:-${GOFR_VAULT_DEV_TOKEN}}"

# Display configuration
echo "=== Auth Manager Configuration ===" >&2
echo "Environment: ${ENV_MODE}" >&2
echo "Backend: ${BACKEND}" >&2
echo "Vault URL: ${GOFR_VAULT_URL}" >&2
echo "Vault Token: ${GOFR_VAULT_TOKEN}" >&2
echo "=====================================" >&2
echo "" >&2

# Run auth_manager.py with remaining arguments
cd "${SCRIPT_DIR}"
exec uv run --active python auth_manager.py "$@"
