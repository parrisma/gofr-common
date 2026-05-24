#!/usr/bin/env bash

set -euo pipefail

KEYCLOAK_CONTAINER="${KEYCLOAK_CONTAINER:-gofr-sec-keycloak}"
KEYCLOAK_SERVER_URL="${KEYCLOAK_SERVER_URL:-http://gofr-sec-keycloak:8080}"
KEYCLOAK_ADMIN_USER="${KEYCLOAK_ADMIN_USER:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-gofr-dev}"
KEYCLOAK_REALM_IMPORT_PATH="${KEYCLOAK_REALM_IMPORT_PATH:-/opt/keycloak/data/import/gofr-dev-realm.json}"
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-gofr-sec-cli}"
KEYCLOAK_DEV_ENV_FILE="${KEYCLOAK_DEV_ENV_FILE:-/tmp/gofr-sec-dev-keycloak.env}"
GOFR_ADMIN_USERNAME="${GOFR_ADMIN_USERNAME:-gofr_admin}"
GOFR_ADMIN_PASSWORD="${GOFR_ADMIN_PASSWORD:-gofr-admin-pass}"
GOFR_USER_USERNAME="${GOFR_USER_USERNAME:-gofr_user}"
GOFR_USER_PASSWORD="${GOFR_USER_PASSWORD:-gofr-user-pass}"

log() {
    printf '[keycloak-dev] %s\n' "$1"
}

require_running_container() {
    if ! docker ps --format '{{.Names}}' | grep -Fxq "$KEYCLOAK_CONTAINER"; then
        printf 'Keycloak container is not running: %s\n' "$KEYCLOAK_CONTAINER" >&2
        exit 1
    fi
}

wait_for_keycloak() {
    local attempt
    for attempt in $(seq 1 30); do
        if curl -fsS "${KEYCLOAK_SERVER_URL}/realms/master/.well-known/openid-configuration" >/dev/null; then
            return 0
        fi
        sleep 2
    done

    printf 'Keycloak did not become ready at %s\n' "$KEYCLOAK_SERVER_URL" >&2
    exit 1
}

kcadm() {
    docker exec "$KEYCLOAK_CONTAINER" /opt/keycloak/bin/kcadm.sh "$@"
}

lookup_user_id() {
    local username="$1"

    kcadm get users -r "$KEYCLOAK_REALM" -q "username=${username}" | \
        python -c 'import json,sys; users=json.load(sys.stdin); print(users[0]["id"] if users else "")'
}

ensure_user() {
    local username="$1"
    local password="$2"
    local email="$3"
    local first_name="$4"
    local last_name="$5"
    local user_id

    user_id="$(lookup_user_id "$username")"
    if [[ -z "$user_id" ]]; then
        kcadm create users -r "$KEYCLOAK_REALM" \
            -s "username=${username}" \
            -s enabled=true \
            -s "email=${email}" \
            -s emailVerified=true \
            -s "firstName=${first_name}" \
            -s "lastName=${last_name}" >/dev/null
        user_id="$(lookup_user_id "$username")"
    fi

    kcadm update "users/${user_id}" -r "$KEYCLOAK_REALM" \
        -s enabled=true \
        -s "email=${email}" \
        -s emailVerified=true \
        -s "firstName=${first_name}" \
        -s "lastName=${last_name}" >/dev/null
    kcadm set-password -r "$KEYCLOAK_REALM" --username "$username" --new-password "$password" >/dev/null

    printf '%s\n' "$user_id"
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

json_field() {
    local field_name="$1"

    python -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$field_name"
}

decode_jwt_claim() {
    local token="$1"
    local claim_name="$2"

    python - "$token" "$claim_name" <<'PY'
import base64
import json
import sys

token = sys.argv[1]
claim_name = sys.argv[2]
payload = token.split('.')[1]
payload += '=' * (-len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
print(claims[claim_name])
PY
}

main() {
    local admin_access_token
    local admin_sub
    local admin_login_json
    local user_access_token
    local user_sub
    local user_login_json

    require_running_container
    wait_for_keycloak

    log "Authenticating Keycloak admin client"
    kcadm config credentials \
        --server "$KEYCLOAK_SERVER_URL" \
        --realm master \
        --user "$KEYCLOAK_ADMIN_USER" \
        --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null

    if ! kcadm get "realms/${KEYCLOAK_REALM}" >/dev/null 2>&1; then
        log "Creating realm ${KEYCLOAK_REALM} from ${KEYCLOAK_REALM_IMPORT_PATH}"
        kcadm create realms -f "$KEYCLOAK_REALM_IMPORT_PATH" >/dev/null
    fi

    if ! kcadm get clients -r "$KEYCLOAK_REALM" -q "clientId=${KEYCLOAK_CLIENT_ID}" | \
        python -c 'import json,sys; sys.exit(0 if json.load(sys.stdin) else 1)'; then
        printf 'Required Keycloak client is missing from realm %s: %s\n' "$KEYCLOAK_REALM" "$KEYCLOAK_CLIENT_ID" >&2
        exit 1
    fi

    admin_sub="$(ensure_user "$GOFR_ADMIN_USERNAME" "$GOFR_ADMIN_PASSWORD" "${GOFR_ADMIN_USERNAME}@example.com" "GOFR" "Admin")"
    user_sub="$(ensure_user "$GOFR_USER_USERNAME" "$GOFR_USER_PASSWORD" "${GOFR_USER_USERNAME}@example.com" "GOFR" "User")"

    admin_login_json="$(password_login "$GOFR_ADMIN_USERNAME" "$GOFR_ADMIN_PASSWORD")"
    admin_access_token="$(printf '%s' "$admin_login_json" | json_field access_token)"
    user_login_json="$(password_login "$GOFR_USER_USERNAME" "$GOFR_USER_PASSWORD")"
    user_access_token="$(printf '%s' "$user_login_json" | json_field access_token)"

    if [[ -z "$admin_access_token" || -z "$user_access_token" ]]; then
        printf 'Unable to obtain Keycloak access tokens for the dev users\n' >&2
        exit 1
    fi

    if [[ "$(decode_jwt_claim "$admin_access_token" sub)" != "$admin_sub" ]]; then
        printf 'Admin access token subject does not match the created Keycloak user\n' >&2
        exit 1
    fi

    if [[ "$(decode_jwt_claim "$user_access_token" sub)" != "$user_sub" ]]; then
        printf 'User access token subject does not match the created Keycloak user\n' >&2
        exit 1
    fi

    cat >"$KEYCLOAK_DEV_ENV_FILE" <<EOF
export KEYCLOAK_REALM='$KEYCLOAK_REALM'
export KEYCLOAK_CLIENT_ID='$KEYCLOAK_CLIENT_ID'
export GOFR_ADMIN_USERNAME='$GOFR_ADMIN_USERNAME'
export GOFR_ADMIN_PASSWORD='$GOFR_ADMIN_PASSWORD'
export GOFR_ADMIN_SUB='$admin_sub'
export GOFR_USER_USERNAME='$GOFR_USER_USERNAME'
export GOFR_USER_PASSWORD='$GOFR_USER_PASSWORD'
export GOFR_USER_SUB='$user_sub'
EOF

    log "Wrote reusable Keycloak dev environment to $KEYCLOAK_DEV_ENV_FILE"
    printf 'GOFR_ADMIN_SUB=%s\nGOFR_USER_SUB=%s\nKEYCLOAK_DEV_ENV_FILE=%s\n' \
        "$admin_sub" \
        "$user_sub" \
        "$KEYCLOAK_DEV_ENV_FILE"
}

main "$@"