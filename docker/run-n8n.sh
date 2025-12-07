#!/bin/sh

# Usage: ./run-n8n.sh [-r] [-p PORT] [-n NETWORK]
# Options:
#   -r           Recreate n8n_volume (drop and recreate if it exists)
#   -p PORT      Port to expose n8n on (default: 5678 or GOFR_N8N_PORT)
#   -n NETWORK   Docker network to attach to (default: gofr-net or GOFR_DOCKER_NETWORK)
#
# Environment Variables:
#   GOFR_N8N_PORT         - Default port for n8n
#   GOFR_DOCKER_NETWORK   - Default Docker network
#
# Example: ./run-n8n.sh -p 5678 -r -n gofr-net

# Parse command line arguments
RECREATE_VOLUME=false
N8N_PORT="${GOFR_N8N_PORT:-5678}"
NETWORK="${GOFR_DOCKER_NETWORK:-gofr-net}"

while getopts "rp:n:" opt; do
    case $opt in
        r)
            RECREATE_VOLUME=true
            ;;
        p)
            N8N_PORT=$OPTARG
            ;;
        n)
            NETWORK=$OPTARG
            ;;
        \?)
            echo "Usage: $0 [-r] [-p PORT] [-n NETWORK]"
            echo "  -r           Recreate n8n_volume (drop and recreate if it exists)"
            echo "  -p PORT      Port to expose n8n on (default: 5678)"
            echo "  -n NETWORK   Docker network to attach to (default: gofr-net)"
            exit 1
            ;;
    esac
done

# Get timezone (default to UTC if not set)
TIMEZONE="${TIMEZONE:-UTC}"

# Create n8n_share directory on host if it doesn't exist
N8N_SHARE_DIR="${HOME}/n8n_share"
echo "Checking for n8n_share directory at ${N8N_SHARE_DIR}..."
if [ ! -d "$N8N_SHARE_DIR" ]; then
    echo "Creating n8n_share directory..."
    mkdir -p "$N8N_SHARE_DIR"
    echo "Directory created at ${N8N_SHARE_DIR}"
else
    echo "Directory ${N8N_SHARE_DIR} already exists"
fi

# Create docker network if it doesn't exist
echo "Checking for $NETWORK network..."
if ! docker network inspect $NETWORK >/dev/null 2>&1; then
    echo "Creating $NETWORK network..."
    docker network create $NETWORK
else
    echo "Network $NETWORK already exists"
fi

# Volume name (shared across projects)
VOLUME_NAME="gofr-n8n-volume"

# Handle volume creation/recreation
if [ "$RECREATE_VOLUME" = true ]; then
    echo "Recreate flag (-r) detected"
    if docker volume inspect $VOLUME_NAME >/dev/null 2>&1; then
        echo "Removing existing $VOLUME_NAME..."
        docker volume rm $VOLUME_NAME 2>/dev/null || {
            echo "ERROR: Failed to remove $VOLUME_NAME. It may be in use."
            echo "Stop all containers using the volume first."
            exit 1
        }
    fi
    echo "Creating $VOLUME_NAME..."
    docker volume create $VOLUME_NAME
else
    echo "Checking for $VOLUME_NAME..."
    if ! docker volume inspect $VOLUME_NAME >/dev/null 2>&1; then
        echo "Creating $VOLUME_NAME..."
        docker volume create $VOLUME_NAME
    else
        echo "Volume $VOLUME_NAME already exists"
    fi
fi

# Stop and remove existing container if it exists
echo "Stopping existing n8n container..."
docker stop n8n 2>/dev/null || true

echo "Removing existing n8n container..."
docker rm n8n 2>/dev/null || true

echo "Starting n8n container..."
echo "Port: $N8N_PORT"

docker run -d \
    --name n8n \
    --network $NETWORK \
    -p $N8N_PORT:5678 \
    -e GENERIC_TIMEZONE="$TIMEZONE" \
    -e TZ="$TIMEZONE" \
    -e N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true \
    -e N8N_RUNNERS_ENABLED=true \
    -e N8N_LOG_LEVEL=debug \
    -e N8N_LOG_OUTPUT=console \
    -e NODE_FUNCTION_ALLOW_EXTERNAL= \
    -v $VOLUME_NAME:/home/node/.n8n \
    -v "${N8N_SHARE_DIR}":/data/n8n_share \
    docker.n8n.io/n8nio/n8n

if docker ps -q -f name=n8n | grep -q .; then
    echo "Container n8n is now running"
    echo ""
    echo "==================================================================="
    echo "🔧 N8N WORKFLOW AUTOMATION"
    echo ""
    echo "Access from Host Machine:"
    echo "  n8n Web UI:    http://localhost:$N8N_PORT"
    echo ""
    echo "Access from $NETWORK (other containers):"
    echo "  n8n API:       http://n8n:5678"
    echo ""
    echo "Data & Storage:"
    echo "  Volume:        $VOLUME_NAME"
    echo "  Shared Dir:    ${N8N_SHARE_DIR} -> /data/n8n_share"
    echo ""
    echo "Management:"
    echo "  View logs:     docker logs -f n8n"
    echo "  Stop:          docker stop n8n"
    echo "  Recreate:      ./run-n8n.sh -r -p $N8N_PORT"
    echo "==================================================================="
    echo ""
else
    echo "ERROR: Container n8n failed to start"
    docker logs n8n
    exit 1
fi
