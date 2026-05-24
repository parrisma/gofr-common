#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${COMMON_ROOT}/../.." && pwd)"
PORTS_FILE="${COMMON_ROOT}/config/gofr_ports.env"
COMPOSE_FILE="${SCRIPT_DIR}/tools-compose.dev.yml"
COMPOSE_ARGS=(--env-file "$PORTS_FILE" -f "$COMPOSE_FILE")
COMPOSE_PROJECT="gofr-tools-dev"
SECRETS_DIR="${PROJECT_ROOT}/secrets"
TOOLS_ENV_FILE="${SECRETS_DIR}/tools-dev-secrets.env"
OPENROUTER_VAULT_PATH="${OPENROUTER_VAULT_PATH:-secret/gofr/config/api-keys/openrouter}"
VAULT_ROOT_TOKEN="${GOFR_SEC_DEV_VAULT_TOKEN:-gofr-dev-root-token}"

log() {
    printf '[tools-dev] %s\n' "$1"
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

ensure_network() {
    if ! docker network inspect gofr-net >/dev/null 2>&1; then
        log 'Creating docker network gofr-net'
        docker network create gofr-net >/dev/null
    fi
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

ensure_volume() {
    local volume_name="$1"

    if ! docker volume inspect "$volume_name" >/dev/null 2>&1; then
        log "Creating docker volume ${volume_name}"
        docker volume create "$volume_name" >/dev/null
    fi
}

ensure_volumes() {
    ensure_volume gofr-openwebui-data
    ensure_volume gofr-n8n-data
    ensure_volume gofr-n8n-logs
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

reconcile_containers() {
    remove_conflicting_container gofr-openwebui
    remove_conflicting_container gofr-n8n
}

ensure_images() {
    if ! docker image inspect gofr-openwebui:dev >/dev/null 2>&1; then
        log 'Building gofr-openwebui:dev'
        bash "${SCRIPT_DIR}/openwebui/build.sh"
    fi

    if ! docker image inspect gofr-n8n:dev >/dev/null 2>&1; then
        log 'Building gofr-n8n:dev'
        bash "${SCRIPT_DIR}/n8n/build.sh"
    fi
}

load_or_create_secrets() {
    mkdir -p "$SECRETS_DIR"

    if [[ -f "$TOOLS_ENV_FILE" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "$TOOLS_ENV_FILE"
        set +a
    fi

    sync_n8n_encryption_key_from_volume

    if [[ -z "${WEBUI_SECRET_KEY:-}" ]]; then
        export WEBUI_SECRET_KEY="$(openssl rand -hex 32)"
    fi

    if [[ -z "${N8N_ENCRYPTION_KEY:-}" ]]; then
        export N8N_ENCRYPTION_KEY="$(openssl rand -hex 32)"
    fi

    cat >"$TOOLS_ENV_FILE" <<EOF
WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY}
N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
EOF
    chmod 600 "$TOOLS_ENV_FILE"
}

sync_n8n_encryption_key_from_volume() {
    local volume_config
    local volume_key

    if ! docker volume inspect gofr-n8n-data >/dev/null 2>&1; then
        return 0
    fi

    volume_config="$(docker run --rm -v gofr-n8n-data:/home/node/.n8n alpine:3.20 sh -lc 'cat /home/node/.n8n/config 2>/dev/null || true')"
    if [[ -z "$volume_config" ]]; then
        return 0
    fi

    volume_key="$(printf '%s' "$volume_config" | tr -d '\n' | sed -n 's/.*"encryptionKey"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
    if [[ -z "$volume_key" ]]; then
        return 0
    fi

    if [[ "${N8N_ENCRYPTION_KEY:-}" != "$volume_key" ]]; then
        log 'Using persisted n8n encryption key from gofr-n8n-data volume'
    fi

    export N8N_ENCRYPTION_KEY="$volume_key"
}

load_openrouter_key() {
    if ! docker ps --filter 'name=gofr-sec-vault' --filter 'status=running' -q | grep -q .; then
        return 0
    fi

    local openrouter_api_key
    openrouter_api_key="$(docker exec \
        -e VAULT_ADDR=http://127.0.0.1:8200 \
        -e VAULT_TOKEN="${VAULT_ROOT_TOKEN}" \
        gofr-sec-vault \
        vault kv get -field=value "${OPENROUTER_VAULT_PATH}" 2>/dev/null || true)"

    if [[ -n "$openrouter_api_key" ]]; then
        export OPENROUTER_API_KEY="$openrouter_api_key"
        log 'Loaded OpenRouter API key from Vault'
    fi
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
    require_command openssl
    load_ports
    require_env_var GOFR_OPENWEBUI_PORT_DEV
    require_env_var GOFR_N8N_PORT_DEV
    ensure_network
    ensure_volumes
    ensure_images
    load_or_create_secrets
    load_openrouter_key
    reconcile_containers

    docker compose "${COMPOSE_ARGS[@]}" config >/dev/null
    docker compose "${COMPOSE_ARGS[@]}" up -d

    wait_for_http 'http://gofr-openwebui:8080/health'
    wait_for_http 'http://gofr-n8n:5678/healthz'

    docker compose "${COMPOSE_ARGS[@]}" ps

    echo
    show_current_container_network
    echo
    log 'Connection endpoints from the host'
    printf '  %-28s %s\n' 'OpenWebUI' "http://localhost:${GOFR_OPENWEBUI_PORT_DEV}"
    printf '  %-28s %s\n' 'n8n editor' "http://localhost:${GOFR_N8N_PORT_DEV}"

    echo
    log 'Connection endpoints from containers on gofr-net'
    show_endpoint 'OpenWebUI' "http://localhost:${GOFR_OPENWEBUI_PORT_DEV}" 'http://gofr-openwebui:8080'
    show_endpoint 'n8n editor' "http://localhost:${GOFR_N8N_PORT_DEV}" 'http://gofr-n8n:5678'

    log "Tools stack is ready"
}

main "$@"