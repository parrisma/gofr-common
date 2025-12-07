#!/bin/sh

# Usage: ./build-openwebui.sh
# Builds the Open WebUI Docker image using Dockerfile.openwebui
# Example: ./build-openwebui.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKERFILE_PATH="$SCRIPT_DIR/Dockerfile.openwebui"
IMAGE_NAME="openwebui:latest"

if [ ! -f "$DOCKERFILE_PATH" ]; then
    echo "ERROR: Dockerfile.openwebui not found in $SCRIPT_DIR"
    exit 1
fi

echo "Building Open WebUI Docker image..."
docker build -t $IMAGE_NAME -f "$DOCKERFILE_PATH" "$SCRIPT_DIR"

echo "Build complete. Image tagged as $IMAGE_NAME"
