#!/bin/bash
# =======================================================================
# ChromaDB Run Script
# =======================================================================

set -e

# Source port configuration if available
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORTS_CONFIG="${SCRIPT_DIR}/../../../config/gofr_ports.sh"
if [[ -f "${PORTS_CONFIG}" ]]; then
    source "${PORTS_CONFIG}"
fi

DOCKER_NETWORK="${GOFR_NETWORK:-gofr-net}"
CHROMA_PORT="${GOFR_CHROMA_PORT:-8000}"
CONTAINER_NAME="gofr-chroma"

# Parse arguments
while getopts "n:p:" opt; do
    case $opt in
        n) DOCKER_NETWORK=$OPTARG ;;
        p) CHROMA_PORT=$OPTARG ;;
        \?) echo "Usage: $0 [-n NETWORK] [-p PORT]"; exit 1 ;;
    esac
done

echo "======================================================================="
echo "Starting GOFR ChromaDB Container"
echo "======================================================================="

# Create network if needed
if ! docker network inspect ${DOCKER_NETWORK} >/dev/null 2>&1; then
    echo "Creating network: ${DOCKER_NETWORK}"
    docker network create ${DOCKER_NETWORK}
fi

# Create volume if needed
if ! docker volume inspect gofr-chroma-data >/dev/null 2>&1; then
    echo "Creating volume: gofr-chroma-data"
    docker volume create gofr-chroma-data
fi

# Stop existing container
if docker ps -aq -f name=${CONTAINER_NAME} | grep -q .; then
    echo "Stopping existing container..."
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
fi

echo ""
echo "Configuration:"
echo "  Network:  ${DOCKER_NETWORK}"
echo "  Port:     ${CHROMA_PORT} -> 8000"
echo "  Data:     gofr-chroma-data"
echo ""

# Run container
docker run -d \
    --name ${CONTAINER_NAME} \
    --network ${DOCKER_NETWORK} \
    --restart unless-stopped \
    -v gofr-chroma-data:/chroma/chroma \
    -p ${CHROMA_PORT}:8000 \
    gofr-chroma:latest

sleep 3

if docker ps -q -f name=${CONTAINER_NAME} | grep -q .; then
    echo "======================================================================="
    echo "Container started: ${CONTAINER_NAME}"
    echo "======================================================================="
    echo ""
    echo "Endpoints:"
    echo "  API:        http://localhost:${CHROMA_PORT}/api/v1"
    echo "  Heartbeat:  http://localhost:${CHROMA_PORT}/api/v1/heartbeat"
    echo ""
    echo "From other containers on ${DOCKER_NETWORK}:"
    echo "  Chroma URL: http://gofr-chroma:8000"
    echo "======================================================================="
else
    echo "ERROR: Container failed to start"
    docker logs ${CONTAINER_NAME}
    exit 1
fi
