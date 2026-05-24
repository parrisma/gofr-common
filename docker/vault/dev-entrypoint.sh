#!/usr/bin/env sh

set -eu

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

root_token="${VAULT_DEV_ROOT_TOKEN_ID:-gofr-dev-root-token}"
listen_address="${VAULT_DEV_LISTEN_ADDRESS:-0.0.0.0:8200}"

printf '[vault-dev] Starting ephemeral unlocked Vault\n'
printf '[vault-dev] Listen address: %s\n' "$listen_address"
printf '[vault-dev] Root token id: %s\n' "$root_token"

exec vault server \
    -dev \
    -dev-root-token-id="$root_token" \
    -dev-listen-address="$listen_address"