#!/bin/bash
# Build n8n Docker image (shared across all GOFR projects)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IMAGE_NAME="gofr-n8n"
IMAGE_TAG="latest"

echo "======================================================================="
echo "Building n8n Docker image"
echo "======================================================================="
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""

docker build \
    -f "${SCRIPT_DIR}/Dockerfile.n8n" \
    -t "${IMAGE_NAME}:${IMAGE_TAG}" \
    "${SCRIPT_DIR}"

echo ""
echo "======================================================================="
echo "Build complete: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "======================================================================="
echo ""
echo "To run n8n:"
echo "  ./run-n8n.sh"
