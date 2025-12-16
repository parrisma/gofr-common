#!/bin/bash
# Run GOFR-Common development container for testing
# Uses gofr-common-dev:latest image (built from gofr-base:latest)
# Standard user: gofr (UID 1000, GID 1000)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Standard GOFR user - all projects use same user
GOFR_USER="gofr"
GOFR_UID=1000
GOFR_GID=1000

# Container and image names
CONTAINER_NAME="gofr-common-dev"
IMAGE_NAME="gofr-common-dev:latest"

echo "======================================================================="
echo "Starting GOFR-Common Development Container (Test Only)"
echo "======================================================================="
echo "User: ${GOFR_USER} (UID=${GOFR_UID}, GID=${GOFR_GID})"
echo "======================================================================="

# Stop and remove existing container
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping existing container: $CONTAINER_NAME"
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
fi

# Run container (with Docker socket for sibling containers)
docker run -d \
    --name "$CONTAINER_NAME" \
    -v "$PROJECT_ROOT:/home/gofr/devroot/gofr-common:rw" \
    -v /var/run/docker.sock:/var/run/docker.sock:rw \
    -e GOFRCOMMON_ENV=development \
    -e GOFRCOMMON_DEBUG=true \
    -e GOFRCOMMON_LOG_LEVEL=DEBUG \
    "$IMAGE_NAME"

echo ""
echo "======================================================================="
echo "Container started: $CONTAINER_NAME"
echo "======================================================================="
echo ""
echo "Useful commands:"
echo "  docker logs -f $CONTAINER_NAME          # Follow logs"
echo "  docker exec -it $CONTAINER_NAME bash    # Shell access"
echo "  docker stop $CONTAINER_NAME             # Stop container"
echo ""
echo "Run tests:"
echo "  docker exec -it $CONTAINER_NAME bash -c 'source .venv/bin/activate && pytest'"
echo "  docker exec -it $CONTAINER_NAME bash -c 'source .venv/bin/activate && pytest -v tests/'"
