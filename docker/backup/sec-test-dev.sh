#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/sec-compose.dev.yml"
KEYCLOAK_SETUP_SCRIPT="${SCRIPT_DIR}/keycloak/setup-dev-realm.sh"
VAULT_SEED_SCRIPT="${SCRIPT_DIR}/vault/seed-dev-signing-key.sh"
KEYCLOAK_SERVER_URL="${KEYCLOAK_SERVER_URL:-http://gofr-sec-keycloak:8080}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-gofr-dev}"
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-gofr-sec-cli}"
KEYCLOAK_DEV_ENV_FILE="${KEYCLOAK_DEV_ENV_FILE:-/tmp/gofr-sec-dev-keycloak.env}"
VAULT_URL="${VAULT_URL:-http://gofr-sec-vault:8200}"
VAULT_TOKEN="${VAULT_TOKEN:-gofr-dev-root-token}"
VAULT_SIGNING_PATH="${VAULT_SIGNING_PATH:-gofr/sec/signing/runtime}"
AUTO_START=true

if [[ "${1:-}" == "--no-start" ]]; then
    AUTO_START=false
fi

log() {
    printf '[sec-test-dev] %s\n' "$1"
}

ensure_network() {
    if ! docker network inspect gofr-net >/dev/null 2>&1; then
        log 'Creating missing Docker network gofr-net'
        docker network create gofr-net >/dev/null
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

json_field() {
    local field_name="$1"

    python -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$field_name"
}

password_login() {
    local username="$1"
    local password="$2"

    curl -fsS "${KEYCLOAK_SERVER_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token" \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        -d "client_id=${KEYCLOAK_CLIENT_ID}" \
        -d 'grant_type=password' \
        -d "username=${username}" \
        -d "password=${password}"
}

main() {
    local admin_access_token
    local admin_login_json
    local user_access_token
    local user_login_json

    ensure_network

    if [[ "$AUTO_START" == true ]]; then
        log 'Starting sec dev stack'
        bash "${SCRIPT_DIR}/keycloak/build.sh"
        bash "${SCRIPT_DIR}/vault/build.sh" --dev
        docker compose -f "$COMPOSE_FILE" up -d
    fi

    docker compose -f "$COMPOSE_FILE" ps
    wait_for_http "${KEYCLOAK_SERVER_URL}/realms/master/.well-known/openid-configuration"
    wait_for_http "${VAULT_URL}/v1/sys/health"

    "$KEYCLOAK_SETUP_SCRIPT" >/dev/null
    "$VAULT_SEED_SCRIPT" >/dev/null
    # shellcheck disable=SC1090
    source "$KEYCLOAK_DEV_ENV_FILE"

    admin_login_json="$(password_login "$GOFR_ADMIN_USERNAME" "$GOFR_ADMIN_PASSWORD")"
    admin_access_token="$(printf '%s' "$admin_login_json" | json_field access_token)"
    user_login_json="$(password_login "$GOFR_USER_USERNAME" "$GOFR_USER_PASSWORD")"
    user_access_token="$(printf '%s' "$user_login_json" | json_field access_token)"

    if [[ -z "$admin_access_token" || -z "$user_access_token" ]]; then
        printf 'Unable to obtain Keycloak access tokens for the dev users\n' >&2
        exit 1
    fi

    cd "$REPO_ROOT"
    ADMIN_ACCESS_TOKEN="$admin_access_token" \
    USER_ACCESS_TOKEN="$user_access_token" \
    KEYCLOAK_REALM="$KEYCLOAK_REALM" \
    KEYCLOAK_CLIENT_ID="$KEYCLOAK_CLIENT_ID" \
    VAULT_URL="$VAULT_URL" \
    VAULT_TOKEN="$VAULT_TOKEN" \
    VAULT_SIGNING_PATH="$VAULT_SIGNING_PATH" \
    GOFR_ADMIN_SUB="$GOFR_ADMIN_SUB" \
    GOFR_USER_SUB="$GOFR_USER_SUB" \
    uv run python - <<'PY'
import base64
import json
import os
import sys
import urllib.request


def decode_claims(token: str) -> dict[str, object]:
    payload = token.split('.')[1]
    payload += '=' * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def audience_contains(aud: object, expected: str) -> bool:
    if isinstance(aud, str):
        return aud == expected
    if isinstance(aud, list):
        return expected in aud
    return False


def fetch_json(url: str, *, headers: dict[str, str] | None = None) -> dict[str, object]:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


client_id = os.environ['KEYCLOAK_CLIENT_ID']
admin_claims = decode_claims(os.environ['ADMIN_ACCESS_TOKEN'])
user_claims = decode_claims(os.environ['USER_ACCESS_TOKEN'])

if admin_claims.get('sub') != os.environ['GOFR_ADMIN_SUB']:
    raise SystemExit('Admin token subject does not match the provisioned Keycloak user')
if user_claims.get('sub') != os.environ['GOFR_USER_SUB']:
    raise SystemExit('User token subject does not match the provisioned Keycloak user')
if not audience_contains(admin_claims.get('aud'), client_id):
    raise SystemExit('Admin token audience is missing the expected gofr-sec client id')
if not audience_contains(user_claims.get('aud'), client_id):
    raise SystemExit('User token audience is missing the expected gofr-sec client id')

vault_health = fetch_json(f"{os.environ['VAULT_URL'].rstrip('/')}/v1/sys/health")
signing_payload = fetch_json(
    f"{os.environ['VAULT_URL'].rstrip('/')}/v1/secret/data/{os.environ['VAULT_SIGNING_PATH']}",
    headers={'X-Vault-Token': os.environ['VAULT_TOKEN']},
)
signing_secret = signing_payload['data']['data']
if not isinstance(signing_secret.get('private_key_pem'), str) or not signing_secret['private_key_pem'].strip():
    raise SystemExit('Vault signing key material is missing from the expected dev path')

summary = {
    'keycloak': {
        'realm': os.environ['KEYCLOAK_REALM'],
        'client_id': client_id,
        'admin_sub': admin_claims['sub'],
        'user_sub': user_claims['sub'],
    },
    'vault': {
        'initialized': vault_health.get('initialized'),
        'sealed': vault_health.get('sealed'),
        'vault_signing_path': os.environ['VAULT_SIGNING_PATH'],
        'kid': signing_secret.get('kid'),
    },
    'ready_for_gofr_sec': True,
}
print(json.dumps(summary, indent=2))
PY
}

main "$@"