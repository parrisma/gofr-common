#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

IMAGE_NAME="gofr-keycloak"
NO_CACHE=""

ensure_base_image_if_needed() {
    local dockerfile_path="$1"

    if ! grep -Eq '^FROM[[:space:]]+gofr-base([:@[:space:]]|$)' "$COMMON_ROOT/$dockerfile_path"; then
        return 0
    fi

    if docker image inspect gofr-base:latest >/dev/null 2>&1; then
        return 0
    fi

    bash "$COMMON_ROOT/docker/base/build.sh"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--no-cache]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

echo "======================================================================="
echo "Building Keycloak Dev Docker image"
echo "======================================================================="
echo "Image: ${IMAGE_NAME}:dev"
echo "Context: ${COMMON_ROOT}"
echo "Dockerfile: ${COMMON_ROOT}/docker/keycloak/Dockerfile.dev"
echo ""

cd "$COMMON_ROOT"
ensure_base_image_if_needed "docker/keycloak/Dockerfile.dev"
docker build \
    ${NO_CACHE} \
    -f docker/keycloak/Dockerfile.dev \
    -t "${IMAGE_NAME}:dev" \
    .

echo ""
echo "======================================================================="
echo "Build complete!"
echo "======================================================================="
echo ""
docker images "${IMAGE_NAME}" --format "{{.Repository}}:{{.Tag}} ({{.Size}})" | grep -E "dev"