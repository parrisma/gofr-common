#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VAULT_URL="${VAULT_URL:-http://gofr-sec-vault:8200}"
VAULT_TOKEN="${VAULT_TOKEN:-gofr-dev-root-token}"
VAULT_SIGNING_PATH="${VAULT_SIGNING_PATH:-gofr/sec/signing/runtime}"
VAULT_FORCE_ROTATE="${VAULT_FORCE_ROTATE:-false}"

log() {
    printf '[vault-dev] %s\n' "$1"
}

wait_for_vault() {
    local attempt
    for attempt in $(seq 1 30); do
        if curl -fsS "${VAULT_URL}/v1/sys/health" >/dev/null; then
            return 0
        fi
        sleep 2
    done

    printf 'Vault did not become ready at %s\n' "$VAULT_URL" >&2
    exit 1
}

main() {
    wait_for_vault

    log "Ensuring runtime signing material exists at ${VAULT_SIGNING_PATH}"
    cd "$REPO_ROOT"

    uv run python - "$VAULT_URL" "$VAULT_TOKEN" "$VAULT_SIGNING_PATH" "$VAULT_FORCE_ROTATE" <<'PY'
import hashlib
import json
import sys
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def fetch_json(url: str, *, headers: dict[str, str]) -> tuple[int, dict[str, object] | None]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 404, None
        raise


vault_url = sys.argv[1].rstrip('/')
vault_token = sys.argv[2]
vault_path = sys.argv[3]
force_rotate = sys.argv[4].lower() == 'true'
headers = {'X-Vault-Token': vault_token}
secret_url = f"{vault_url}/v1/secret/data/{vault_path}"

status, payload = fetch_json(secret_url, headers=headers)
if status == 200 and not force_rotate:
    secret = payload['data']['data']
    print(json.dumps({
        'action': 'kept',
        'vault_path': vault_path,
        'kid': secret.get('kid'),
    }, indent=2))
    raise SystemExit(0)

private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
private_key_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode('ascii')
public_key_pem = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode('ascii')
kid = hashlib.sha256(public_key_pem.encode('ascii')).hexdigest()[:16]

write_request = urllib.request.Request(
    secret_url,
    data=json.dumps({'data': {'private_key_pem': private_key_pem, 'kid': kid}}).encode('utf-8'),
    headers={**headers, 'Content-Type': 'application/json'},
    method='POST',
)
with urllib.request.urlopen(write_request) as response:
    result = json.load(response)

print(json.dumps({
    'action': 'seeded' if status == 404 else 'rotated',
    'vault_path': vault_path,
    'kid': kid,
    'version': result['data']['version'],
}, indent=2))
PY
}

main "$@"