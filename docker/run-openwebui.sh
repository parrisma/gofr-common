#!/bin/sh

# Usage: ./run-openwebui.sh [-r] [-p PORT] [-n NETWORK]
# Options:
#   -r             Recreate openwebui_volume (drop and recreate if it exists)
#   -p PORT        Port to expose Open WebUI on (default: 9090 or GOFR_WEBUI_PORT)
#   -n NETWORK     Docker network to attach to (default: gofr-net or GOFR_DOCKER_NETWORK)
#
# Environment Variables:
#   OPENROUTER_API_KEY      - API key for OpenRouter integration
#   GOFR_WEBUI_PORT         - Default port for Open WebUI
#   GOFR_DOCKER_NETWORK     - Default Docker network
#
# Example: ./run-openwebui.sh -r -p 9090 -n gofr-net

RECREATE_VOLUME=false
WEBUI_PORT="${GOFR_WEBUI_PORT:-9090}"
DOCKER_NETWORK="${GOFR_DOCKER_NETWORK:-gofr-net}"

while getopts "rp:n:" opt; do
    case $opt in
        r)
            RECREATE_VOLUME=true
        ;;
        p)
            WEBUI_PORT=$OPTARG
        ;;
        n)
            DOCKER_NETWORK=$OPTARG
        ;;
        \?)
            echo "Usage: $0 [-r] [-p PORT] [-n NETWORK]"
            echo "  -r             Recreate openwebui_volume (drop and recreate if it exists)"
            echo "  -p PORT        Port to expose Open WebUI on (default: 9090)"
            echo "  -n NETWORK     Docker network to attach to (default: gofr-net)"
            exit 1
        ;;
    esac
done

TIMEZONE="${TIMEZONE:-UTC}"

# OpenRouter API Key (set via environment variable or default to empty)
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"

# Create openwebui_share directory on host if it doesn't exist
WEBUI_SHARE_DIR="${HOME}/openwebui_share"
echo "Checking for openwebui_share directory at ${WEBUI_SHARE_DIR}..."
if [ ! -d "$WEBUI_SHARE_DIR" ]; then
    echo "Creating openwebui_share directory..."
    mkdir -p "$WEBUI_SHARE_DIR"
    echo "Directory created at ${WEBUI_SHARE_DIR}"
else
    echo "Directory ${WEBUI_SHARE_DIR} already exists"
fi

# Create docker network if it doesn't exist
if ! docker network inspect $DOCKER_NETWORK >/dev/null 2>&1; then
    echo "Creating $DOCKER_NETWORK network..."
    docker network create $DOCKER_NETWORK
else
    echo "Network $DOCKER_NETWORK already exists"
fi

# Handle openwebui_volume creation/recreation
if [ "$RECREATE_VOLUME" = true ]; then
    echo "Recreate flag (-r) detected"
    if docker volume inspect openwebui_volume >/dev/null 2>&1; then
        echo "Removing existing openwebui_volume..."
        docker volume rm openwebui_volume 2>/dev/null || {
            echo "ERROR: Failed to remove openwebui_volume. It may be in use."
            echo "Stop all containers using the volume first."
            exit 1
        }
    fi
    echo "Creating openwebui_volume..."
    docker volume create openwebui_volume
else
    if ! docker volume inspect openwebui_volume >/dev/null 2>&1; then
        echo "Creating openwebui_volume..."
        docker volume create openwebui_volume
    else
        echo "Volume openwebui_volume already exists"
    fi
fi

# Check if custom openwebui image exists
if ! docker image inspect openwebui:latest >/dev/null 2>&1; then
    echo "ERROR: openwebui:latest image not found."
    echo "Build it first with: ./docker/build-openwebui.sh"
    exit 1
fi

# Stop and remove existing container if it exists
echo "Stopping existing openwebui container..."
docker stop openwebui 2>/dev/null || true

echo "Removing existing openwebui container..."
docker rm openwebui 2>/dev/null || true

echo "Starting openwebui container..."
echo "Port: $WEBUI_PORT"

# Build docker run command
DOCKER_CMD="docker run -d \
--name openwebui \
--network $DOCKER_NETWORK \
-p 0.0.0.0:$WEBUI_PORT:8080 \
-e TZ=\"$TIMEZONE\""

# Add OpenRouter configuration if API key is provided
if [ -n "$OPENROUTER_API_KEY" ]; then
    echo "Configuring OpenRouter API key..."
    DOCKER_CMD="$DOCKER_CMD \
    -e OPENAI_API_BASE_URL=https://openrouter.ai/api/v1 \
    -e OPENAI_API_KEY=\"$OPENROUTER_API_KEY\" \
    -e ENABLE_OPENAI_API=true"
fi

# Enable direct connections to OpenAI-compatible endpoints
DOCKER_CMD="$DOCKER_CMD \
-e ENABLE_API_KEY_AUTH=true"

DOCKER_CMD="$DOCKER_CMD \
-v openwebui_volume:/data \
-v \"${WEBUI_SHARE_DIR}\":/data/openwebui_share \
--restart unless-stopped \
openwebui:latest"

# Execute the docker run command
eval $DOCKER_CMD

if docker ps -q -f name=openwebui | grep -q .; then
    echo "Container openwebui is now running"
    echo ""
    echo "==================================================================="
    echo "🌐 OPEN WEB UI ACCESS:"
    echo ""
    echo "From Your Browser (Host Machine):"
    echo "  👉 http://localhost:$WEBUI_PORT"
    echo ""
    if [ -n "$OPENROUTER_API_KEY" ]; then
        echo "✅ OpenRouter API configured"
        echo "   Base URL: https://openrouter.ai/api/v1"
        echo "   API Key:  ${OPENROUTER_API_KEY:0:8}...${OPENROUTER_API_KEY: -4}"
    else
        echo "ℹ️  OpenRouter not configured"
        echo "   To enable: export OPENROUTER_API_KEY=your_key_here"
        echo "   Then re-run: ./docker/run-openwebui.sh"
    fi
    echo ""
    echo "From WSL2 Host (Windows):"
    echo "  👉 http://\$(ip addr show eth0 | grep 'inet ' | awk '{print \$2}' | cut -d/ -f1):$WEBUI_PORT"
    echo ""
    echo "From Containers on $DOCKER_NETWORK:"
    echo "  http://openwebui:8080"
    echo ""
    echo "-------------------------------------------------------------------"
    echo "Data & Storage:"
    echo "  Volume:        openwebui_volume"
    echo "  Shared Dir:    ${WEBUI_SHARE_DIR} -> /data/openwebui_share"
    echo "  Network:       $DOCKER_NETWORK"
    echo ""
    echo "Management:"
    echo "  View logs:     docker logs -f openwebui"
    echo "  Stop:          docker stop openwebui"
    echo "  Recreate:      ./docker/run-openwebui.sh -r -p $WEBUI_PORT -n $DOCKER_NETWORK"
    echo "==================================================================="
    echo ""
else
    echo "ERROR: Container openwebui failed to start"
    docker logs openwebui
    exit 1
fi
