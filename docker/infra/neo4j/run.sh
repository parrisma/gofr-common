#!/bin/bash
# =======================================================================
# Neo4j Run Script
# =======================================================================

set -e

# Source port configuration if available
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORTS_CONFIG="${SCRIPT_DIR}/../../../config/gofr_ports.sh"
if [[ -f "${PORTS_CONFIG}" ]]; then
    source "${PORTS_CONFIG}"
fi

DOCKER_NETWORK="${GOFR_NETWORK:-gofr-net}"
HTTP_PORT="${GOFR_NEO4J_HTTP_PORT:-7474}"
BOLT_PORT="${GOFR_NEO4J_BOLT_PORT:-7687}"
CONTAINER_NAME="gofr-neo4j"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-gofr-neo4j-password}"

# Parse arguments
while getopts "n:h:b:p:" opt; do
    case $opt in
        n) DOCKER_NETWORK=$OPTARG ;;
        h) HTTP_PORT=$OPTARG ;;
        b) BOLT_PORT=$OPTARG ;;
        p) NEO4J_PASSWORD=$OPTARG ;;
        \?) echo "Usage: $0 [-n NETWORK] [-h HTTP_PORT] [-b BOLT_PORT] [-p PASSWORD]"; exit 1 ;;
    esac
done

echo "======================================================================="
echo "Starting GOFR Neo4j Container"
echo "======================================================================="

# Create network if needed
if ! docker network inspect ${DOCKER_NETWORK} >/dev/null 2>&1; then
    echo "Creating network: ${DOCKER_NETWORK}"
    docker network create ${DOCKER_NETWORK}
fi

# Create volumes if needed
for vol in gofr-neo4j-data gofr-neo4j-logs; do
    if ! docker volume inspect ${vol} >/dev/null 2>&1; then
        echo "Creating volume: ${vol}"
        docker volume create ${vol}
    fi
done

# Stop existing container
if docker ps -aq -f name=${CONTAINER_NAME} | grep -q .; then
    echo "Stopping existing container..."
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
fi

echo ""
echo "Configuration:"
echo "  Network:    ${DOCKER_NETWORK}"
echo "  HTTP Port:  ${HTTP_PORT} -> 7474"
echo "  Bolt Port:  ${BOLT_PORT} -> 7687"
echo "  Data:       gofr-neo4j-data"
echo "  Logs:       gofr-neo4j-logs"
echo ""

# Run container
docker run -d \
    --name ${CONTAINER_NAME} \
    --network ${DOCKER_NETWORK} \
    --restart unless-stopped \
    -v gofr-neo4j-data:/data \
    -v gofr-neo4j-logs:/logs \
    -p ${HTTP_PORT}:7474 \
    -p ${BOLT_PORT}:7687 \
    -e NEO4J_AUTH=neo4j/${NEO4J_PASSWORD} \
    gofr-neo4j:latest

sleep 3

if docker ps -q -f name=${CONTAINER_NAME} | grep -q .; then
    echo "======================================================================="
    echo "Container started: ${CONTAINER_NAME}"
    echo "======================================================================="
    echo ""
    echo "Endpoints:"
    echo "  Browser:  http://localhost:${HTTP_PORT}"
    echo "  Bolt:     bolt://localhost:${BOLT_PORT}"
    echo ""
    echo "Credentials:"
    echo "  Username: neo4j"
    echo "  Password: ${NEO4J_PASSWORD}"
    echo ""
    echo "From other containers on ${DOCKER_NETWORK}:"
    echo "  Bolt URI: bolt://gofr-neo4j:7687"
    echo "======================================================================="
else
    echo "ERROR: Container failed to start"
    docker logs ${CONTAINER_NAME}
    exit 1
fi
