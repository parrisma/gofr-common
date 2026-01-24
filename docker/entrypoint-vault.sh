#!/bin/sh
# Vault Entrypoint for GOFR shared infrastructure
# Starts Vault in production mode with file storage

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo "${BLUE}[VAULT]${NC} $1"; }
log_success() { echo "${GREEN}[VAULT]${NC} $1"; }
log_warn() { echo "${YELLOW}[VAULT]${NC} $1"; }
log_error() { echo "${RED}[VAULT]${NC} $1"; }

main() {
    echo "======================================================================="
    echo "GOFR Shared Vault - Production Mode"
    echo "======================================================================="
    echo "Storage:    File-based (/vault/data)"
    echo "Listen:     ${VAULT_ADDR}"
    echo "Config:     /vault/config/vault.hcl"
    echo "======================================================================="
    
    if [ ! -f "/vault/data/vault.db" ]; then
        log_warn "Fresh install detected - Vault needs initialization"
        log_warn "After startup, run: docker exec gofr-vault vault operator init"
        log_warn "Save the unseal keys and root token securely!"
    else
        log_info "Existing Vault data found"
        log_warn "Vault will need unsealing after startup"
        log_warn "Run: docker exec gofr-vault vault operator unseal"
    fi
    
    log_info "Starting Vault server in production mode..."
    
    # Execute vault server with config file
    exec vault "$@"
}

main "$@"
