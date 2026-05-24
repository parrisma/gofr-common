#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PORTS_FILE="${COMMON_ROOT}/config/gofr_ports.env"
COMPOSE_FILE="${SCRIPT_DIR}/system-compose.dev.yml"
COMPOSE_ARGS=(--env-file "$PORTS_FILE" -f "$COMPOSE_FILE")
COMPOSE_PROJECT="gofr-system-dev"
KEYCLOAK_SETUP_SCRIPT="${SCRIPT_DIR}/keycloak/setup-dev-realm.sh"
VAULT_SEED_SCRIPT="${SCRIPT_DIR}/vault/seed-dev-signing-key.sh"
KEYCLOAK_SERVER_URL="${KEYCLOAK_SERVER_URL:-}"
VAULT_URL="${VAULT_URL:-}"
SEQ_HEALTH_URL="${SEQ_HEALTH_URL:-}"
KEYCLOAK_DEV_ENV_FILE="${KEYCLOAK_DEV_ENV_FILE:-/tmp/gofr-sec-dev-keycloak.env}"
VAULT_SIGNING_PATH="${VAULT_SIGNING_PATH:-gofr/sec/signing/runtime}"

log() {
    printf '[system-dev] %s\n' "$1"
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        printf 'Required command is missing: %s\n' "$1" >&2
        exit 1
    fi
}

require_env_var() {
    local variable_name="$1"

    if [[ -z "${!variable_name:-}" ]]; then
        printf 'Required port variable is missing: %s\n' "$variable_name" >&2
        exit 1
    fi
}

load_ports() {
    if [[ ! -f "$PORTS_FILE" ]]; then
        printf 'Port configuration is missing: %s\n' "$PORTS_FILE" >&2
        exit 1
    fi

    set -a
    # shellcheck disable=SC1090
    source "$PORTS_FILE"
    set +a
}

set_runtime_urls() {
    KEYCLOAK_SERVER_URL="${KEYCLOAK_SERVER_URL:-http://gofr-sec-keycloak:8080}"
    VAULT_URL="${VAULT_URL:-http://gofr-sec-vault:8200}"
    SEQ_HEALTH_URL="${SEQ_HEALTH_URL:-http://gofr-sec-seq/}"
}

show_current_container_network() {
    local current_container
    local networks

    if [[ -z "${HOSTNAME:-}" ]] || ! docker container inspect "$HOSTNAME" >/dev/null 2>&1; then
        return 0
    fi

    current_container="$(docker inspect --format '{{.Name}}' "$HOSTNAME" 2>/dev/null | sed 's#^/##')"
    networks="$(docker inspect --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$HOSTNAME" 2>/dev/null | xargs)"

    if [[ " $networks " == *" gofr-net "* ]]; then
        log "Current container ${current_container} is attached to gofr-net (${networks})"
    else
        log "Current container ${current_container} networks: ${networks}"
    fi
}

ensure_network() {
    if ! docker network inspect gofr-net >/dev/null 2>&1; then
        log 'Creating docker network gofr-net'
        docker network create gofr-net >/dev/null
    fi
}

ensure_images() {
    if ! docker image inspect gofr-keycloak:dev >/dev/null 2>&1; then
        log 'Building gofr-keycloak:dev'
        bash "${SCRIPT_DIR}/keycloak/build.sh"
    fi

    if ! docker image inspect gofr-vault:dev >/dev/null 2>&1; then
        log 'Building gofr-vault:dev'
        bash "${SCRIPT_DIR}/vault/build.sh" --dev
    fi

    if ! docker image inspect gofr-sec-seq:dev >/dev/null 2>&1; then
        log 'Building gofr-sec-seq:dev'
        bash "${SCRIPT_DIR}/seq/build.sh" --dev
    fi
}

remove_conflicting_container() {
    local container_name="$1"
    local compose_project

    if ! docker container inspect "$container_name" >/dev/null 2>&1; then
        return 0
    fi

    compose_project="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$container_name" 2>/dev/null || true)"

    if [[ "$compose_project" == "$COMPOSE_PROJECT" ]]; then
        return 0
    fi

    log "Removing conflicting container ${container_name} from project ${compose_project:-unknown}"
    docker rm -f "$container_name" >/dev/null
}

remove_stale_container() {
    local container_name="$1"

    if ! docker container inspect "$container_name" >/dev/null 2>&1; then
        return 0
    fi

    log "Removing stale container ${container_name}"
    if ! docker rm -f "$container_name" >/dev/null; then
        printf 'Cannot continue while stale container remains: %s\n' "$container_name" >&2
        printf 'The stale container may hold ports or compose service labels needed by this stack.\n' >&2
        printf 'Remove it with: docker rm -f %s\n' "$container_name" >&2
        printf 'If Docker reports no exit event, restart Docker or the host, then retry.\n' >&2
        exit 1
    fi
}

reconcile_containers() {
    remove_conflicting_container gofr-sec-keycloak
    remove_conflicting_container gofr-sec-vault
    remove_conflicting_container gofr-sec-seq
    remove_stale_container gofr-seq-dev
}

wait_for_http() {
    local url="$1"
    local attempt

    for attempt in $(seq 1 30); do
        if curl -fsS "$url" >/dev/null; then
            return 0
        fi
        sleep 2
    done

    printf 'Endpoint did not become ready: %s\n' "$url" >&2
    exit 1
}

show_endpoint() {
    local label="$1"
    local host_url="$2"
    local docker_url="$3"

    printf '  %-28s host: %-36s docker: %s\n' "$label" "$host_url" "$docker_url"
}

main() {
    require_command docker
    require_command curl
    load_ports
    require_env_var GOFR_KEYCLOAK_PORT_DEV
    require_env_var GOFR_VAULT_PORT_DEV
    require_env_var GOFR_SEQ_INGEST_PORT_DEV
    require_env_var GOFR_SEQ_UI_PORT_DEV
    set_runtime_urls
    ensure_network
    ensure_images
    reconcile_containers

    docker compose "${COMPOSE_ARGS[@]}" config >/dev/null
    docker compose "${COMPOSE_ARGS[@]}" up -d

    wait_for_http "${KEYCLOAK_SERVER_URL}/realms/master/.well-known/openid-configuration"
    wait_for_http "${VAULT_URL}/v1/sys/health"
    wait_for_http "$SEQ_HEALTH_URL"

    KEYCLOAK_SERVER_URL="$KEYCLOAK_SERVER_URL" \
    KEYCLOAK_DEV_ENV_FILE="$KEYCLOAK_DEV_ENV_FILE" \
    "$KEYCLOAK_SETUP_SCRIPT" >/dev/null

    VAULT_URL="$VAULT_URL" \
    VAULT_SIGNING_PATH="$VAULT_SIGNING_PATH" \
    "$VAULT_SEED_SCRIPT" >/dev/null

    if [[ -f "$KEYCLOAK_DEV_ENV_FILE" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "$KEYCLOAK_DEV_ENV_FILE"
        set +a
    fi

    docker compose "${COMPOSE_ARGS[@]}" ps

    echo
    show_current_container_network
    echo
    log 'Connection endpoints from the host'
    printf '  %-28s %s\n' 'Keycloak admin console' "http://localhost:${GOFR_KEYCLOAK_PORT_DEV}/admin/"
    printf '  %-28s %s\n' 'Keycloak realm discovery' "http://localhost:${GOFR_KEYCLOAK_PORT_DEV}/realms/gofr-dev/.well-known/openid-configuration"
    printf '  %-28s %s\n' 'Vault UI' "http://localhost:${GOFR_VAULT_PORT_DEV}/ui/"
    printf '  %-28s %s\n' 'Vault API health' "http://localhost:${GOFR_VAULT_PORT_DEV}/v1/sys/health"
    printf '  %-28s %s\n' 'Seq UI' "http://localhost:${GOFR_SEQ_UI_PORT_DEV}"
    printf '  %-28s %s\n' 'Seq ingest' "http://localhost:${GOFR_SEQ_INGEST_PORT_DEV}"

    echo
    log 'Connection endpoints from containers on gofr-net'
    show_endpoint 'Keycloak admin console' "http://localhost:${GOFR_KEYCLOAK_PORT_DEV}/admin/" 'http://gofr-sec-keycloak:8080/admin/'
    show_endpoint 'Keycloak realm discovery' "http://localhost:${GOFR_KEYCLOAK_PORT_DEV}/realms/gofr-dev/.well-known/openid-configuration" 'http://gofr-sec-keycloak:8080/realms/gofr-dev/.well-known/openid-configuration'
    show_endpoint 'Vault UI' "http://localhost:${GOFR_VAULT_PORT_DEV}/ui/" 'http://gofr-sec-vault:8200/ui/'
    show_endpoint 'Vault API health' "http://localhost:${GOFR_VAULT_PORT_DEV}/v1/sys/health" 'http://gofr-sec-vault:8200/v1/sys/health'
    show_endpoint 'Seq UI' "http://localhost:${GOFR_SEQ_UI_PORT_DEV}" 'http://gofr-sec-seq'
    show_endpoint 'Seq ingest' "http://localhost:${GOFR_SEQ_INGEST_PORT_DEV}" 'http://gofr-sec-seq:5341'

    if [[ -n "${GOFR_ADMIN_SUB:-}" ]]; then
        log "GOFR admin subject: ${GOFR_ADMIN_SUB}"
    fi
    if [[ -n "${GOFR_USER_SUB:-}" ]]; then
        log "GOFR user subject: ${GOFR_USER_SUB}"
    fi
    log 'System stack is ready'
}

main "$@"