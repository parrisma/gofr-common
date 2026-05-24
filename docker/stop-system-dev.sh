#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PORTS_FILE="${COMMON_ROOT}/config/gofr_ports.env"
COMPOSE_FILE="${SCRIPT_DIR}/system-compose.dev.yml"
COMPOSE_ARGS=(--env-file "$PORTS_FILE" -f "$COMPOSE_FILE")
REMOVE_VOLUMES=false

if [[ "${1:-}" == "--volumes" ]]; then
    REMOVE_VOLUMES=true
fi

if [[ ! -f "$PORTS_FILE" ]]; then
    printf 'Port configuration is missing: %s\n' "$PORTS_FILE" >&2
    exit 1
fi

if [[ "$REMOVE_VOLUMES" == true ]]; then
    docker compose "${COMPOSE_ARGS[@]}" down --volumes --remove-orphans
else
    docker compose "${COMPOSE_ARGS[@]}" down --remove-orphans
fi