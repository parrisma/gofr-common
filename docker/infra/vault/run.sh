#!/bin/bash
# =======================================================================
# HashiCorp Vault Run Script
# =======================================================================
# Usage:
#   ./run.sh              # Default: dev/test mode (ephemeral)
#   ./run.sh --test       # Explicit test mode (ephemeral, in-memory)
#   ./run.sh --prod       # Production mode (persistent volumes)
#
# Test/Dev Mode:
#   - Auto-initializes and auto-unseals
#   - In-memory storage (data lost on restart)
#   - Known root token for testing
#   - KV v2 secrets engine auto-enabled at 'secret/'
#
# Production Mode:
#   - File storage with persistent volume
#   - Requires manual init and unseal
#   - Logs persisted to volume
#   - Uses vault-config.hcl
#
# Access from other containers on gofr-net:
#   VAULT_ADDR=http://gofr-vault:8200
# =======================================================================

set -e

# Source port configuration if available
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORTS_CONFIG="${SCRIPT_DIR}/../../../config/gofr_ports.sh"
if [[ -f "${PORTS_CONFIG}" ]]; then
    source "${PORTS_CONFIG}"
fi

# Defaults
DOCKER_NETWORK="${GOFR_NETWORK:-gofr-net}"
VAULT_PORT="${GOFR_VAULT_PORT:-8201}"
ROOT_TOKEN="${GOFR_VAULT_DEV_TOKEN:-gofr-dev-root-token}"
MODE="test"  # Default to test mode
CUSTOM_NAME=""  # Optional custom container name

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --test|-t)
            MODE="test"
            shift
            ;;
        --prod|-p)
            MODE="prod"
            shift
            ;;
        --port)
            VAULT_PORT="$2"
            shift 2
            ;;
        --network)
            DOCKER_NETWORK="$2"
            shift 2
            ;;
        --name)
            CUSTOM_NAME="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--test|--prod] [--port PORT] [--network NETWORK] [--name NAME]"
            echo ""
            echo "Modes:"
            echo "  --test, -t    Ephemeral dev mode (default) - in-memory, auto-unsealed"
            echo "  --prod, -p    Production mode - persistent storage, manual unseal"
            echo ""
            echo "Options:"
            echo "  --port PORT       Host port to expose (default: ${VAULT_PORT})"
            echo "  --network NET     Docker network (default: ${DOCKER_NETWORK})"
            echo "  --name NAME       Custom container name (overrides default)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

# Set container name based on mode (or use custom name if provided)
if [[ -n "$CUSTOM_NAME" ]]; then
    CONTAINER_NAME="$CUSTOM_NAME"
elif [[ "$MODE" == "test" ]]; then
    CONTAINER_NAME="gofr-vault"
else
    CONTAINER_NAME="gofr-vault-prod"
fi

echo "======================================================================="
if [[ "$MODE" == "test" ]]; then
    echo "Starting GOFR Vault Container (Test/Dev Mode)"
else
    echo "Starting GOFR Vault Container (Production Mode)"
fi
echo "======================================================================="

# Create network if needed
if ! docker network inspect ${DOCKER_NETWORK} >/dev/null 2>&1; then
    echo "Creating network: ${DOCKER_NETWORK}"
    docker network create ${DOCKER_NETWORK}
fi

# Stop existing container
if docker ps -aq -f name="^${CONTAINER_NAME}$" | grep -q .; then
    echo "Stopping existing container..."
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
fi

echo ""
echo "Configuration:"
echo "  Mode:        ${MODE}"
echo "  Network:     ${DOCKER_NETWORK}"
echo "  Container:   ${CONTAINER_NAME}"
echo "  Port:        ${VAULT_PORT} -> 8200"

if [[ "$MODE" == "test" ]]; then
    # =======================================================================
    # TEST MODE: Ephemeral, in-memory, auto-unsealed
    # =======================================================================
    echo "  Root Token:  ${ROOT_TOKEN}"
    echo "  Storage:     In-memory (ephemeral)"
    echo ""

    docker run -d \
        --name ${CONTAINER_NAME} \
        --network ${DOCKER_NETWORK} \
        --hostname ${CONTAINER_NAME} \
        -p ${VAULT_PORT}:8200 \
        -e VAULT_DEV_ROOT_TOKEN_ID=${ROOT_TOKEN} \
        -e VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:8200 \
        -e VAULT_ADDR=http://127.0.0.1:8200 \
        --cap-add=IPC_LOCK \
        gofr-vault:latest

else
    # =======================================================================
    # PRODUCTION MODE: Persistent volumes, manual unseal
    # =======================================================================
    DATA_VOLUME="gofr-vault-data"
    LOGS_VOLUME="gofr-vault-logs"
    
    # Create volumes if needed
    if ! docker volume inspect ${DATA_VOLUME} >/dev/null 2>&1; then
        echo "Creating volume: ${DATA_VOLUME}"
        docker volume create ${DATA_VOLUME}
    fi
    if ! docker volume inspect ${LOGS_VOLUME} >/dev/null 2>&1; then
        echo "Creating volume: ${LOGS_VOLUME}"
        docker volume create ${LOGS_VOLUME}
    fi
    
    echo "  Storage:     Persistent (${DATA_VOLUME})"
    echo "  Logs:        Persistent (${LOGS_VOLUME})"
    echo ""

    docker run -d \
        --name ${CONTAINER_NAME} \
        --network ${DOCKER_NETWORK} \
        --hostname ${CONTAINER_NAME} \
        -p ${VAULT_PORT}:8200 \
        -v ${DATA_VOLUME}:/vault/data \
        -v ${LOGS_VOLUME}:/vault/logs \
        -v "${SCRIPT_DIR}/vault-config.hcl:/vault/config/vault-config.hcl:ro" \
        -e VAULT_ADDR=http://127.0.0.1:8200 \
        --cap-add=IPC_LOCK \
        gofr-vault:latest \
        server -config=/vault/config/vault-config.hcl
fi

echo ""
echo "Waiting for Vault to be ready..."
sleep 2

# Wait for Vault to be responsive
MAX_ATTEMPTS=30
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if [[ "$MODE" == "test" ]]; then
        if docker exec ${CONTAINER_NAME} vault status >/dev/null 2>&1; then
            echo "Vault is ready and unsealed!"
            break
        fi
    else
        # In prod mode, just check if vault is responding (may be sealed)
        if docker exec ${CONTAINER_NAME} vault status 2>&1 | grep -qE "(Sealed|Key)"; then
            echo "Vault is ready (sealed - requires initialization)"
            break
        elif docker exec ${CONTAINER_NAME} vault status >/dev/null 2>&1; then
            echo "Vault is ready and unsealed!"
            break
        fi
    fi
    ATTEMPT=$((ATTEMPT + 1))
    sleep 1
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "ERROR: Vault failed to start"
    docker logs ${CONTAINER_NAME}
    exit 1
fi

echo ""
echo "======================================================================="
echo "Vault is running!"
echo "======================================================================="
echo "  Container:   ${CONTAINER_NAME}"
echo "  Network:     ${DOCKER_NETWORK}"
echo "  Internal:    http://${CONTAINER_NAME}:8200 (from gofr-net containers)"
echo "  External:    http://localhost:${VAULT_PORT} (from host)"
echo "  UI:          http://localhost:${VAULT_PORT}/ui"

if [[ "$MODE" == "test" ]]; then
    echo "  Root Token:  ${ROOT_TOKEN}"
    echo ""
    echo "  From other containers on gofr-net:"
    echo "    export VAULT_ADDR=http://${CONTAINER_NAME}:8200"
    echo "    export VAULT_TOKEN=${ROOT_TOKEN}"
else
    echo ""
    echo "  PRODUCTION MODE - Manual initialization required:"
    echo ""
    echo "  1. Initialize Vault (first time only):"
    echo "     docker exec ${CONTAINER_NAME} vault operator init"
    echo ""
    echo "  2. Unseal Vault (after each restart):"
    echo "     docker exec -it ${CONTAINER_NAME} vault operator unseal"
    echo "     (repeat 3 times with different unseal keys)"
    echo ""
    echo "  3. From other containers on gofr-net:"
    echo "     export VAULT_ADDR=http://${CONTAINER_NAME}:8200"
    echo "     export VAULT_TOKEN=<your-root-token>"
fi
echo "======================================================================="
