#!/bin/bash
# =============================================================================
# GOFR Auth Bootstrap Wrapper Script
# =============================================================================
# Bootstrap authentication for GOFR projects by creating reserved groups
# (public, admin) and generating bootstrap tokens.
#
# This script:
# 1. Sources port configuration from gofr_ports.sh
# 2. Sets up environment variables for the specified project
# 3. Calls bootstrap_auth.py to create groups and tokens
#
# Usage:
#   # Bootstrap with default prefix (GOFR)
#   ./bootstrap_auth.sh
#
#   # Bootstrap for specific project
#   ./bootstrap_auth.sh --prefix GOFR
#
#   # Bootstrap groups only (no tokens)
#   ./bootstrap_auth.sh --groups-only
#
#   # Capture tokens to file
#   ./bootstrap_auth.sh --prefix GOFR > tokens.env
#   source tokens.env
#
#   # Use with eval for current shell
#   eval "$(./bootstrap_auth.sh --prefix GOFR)"
#
# Environment Variables (can be set before running):
#   GOFR_AUTH_PREFIX       Default prefix if --prefix not specified
#   GOFR_VAULT_URL         Vault server URL (default: http://gofr-vault:8200)
#   GOFR_VAULT_TOKEN       Vault token (default: from gofr_ports.sh)
#   GOFR_JWT_SECRET        JWT signing secret (auto-generated if not set)
#
# =============================================================================

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOFR_COMMON_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Source port configuration if available
GOFR_PORTS_SH="${GOFR_COMMON_ROOT}/config/gofr_ports.sh"
if [[ -f "$GOFR_PORTS_SH" ]]; then
    source "$GOFR_PORTS_SH"
fi

# Parse command line for --prefix to set up project-specific defaults
PREFIX="GOFR"
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --prefix)
            PREFIX="$2"
            EXTRA_ARGS+=("$1" "$2")
            shift 2
            ;;
        --prefix=*)
            PREFIX="${1#*=}"
            EXTRA_ARGS+=("$1")
            shift
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

# Normalize prefix
PREFIX="${PREFIX^^}"  # uppercase
PREFIX="${PREFIX%%_}" # remove trailing underscore if present

# Build dynamic variable names
VAULT_URL_VAR="${PREFIX}_VAULT_URL"
VAULT_TOKEN_VAR="${PREFIX}_VAULT_TOKEN"
AUTH_BACKEND_VAR="${PREFIX}_AUTH_BACKEND"
VAULT_PATH_PREFIX_VAR="${PREFIX}_VAULT_PATH_PREFIX"
VAULT_MOUNT_POINT_VAR="${PREFIX}_VAULT_MOUNT_POINT"

# Set default environment variables based on prefix
# Use dynamic variable assignment with proper default handling

# Vault URL - use gofr_ports.sh port if available
DEFAULT_VAULT_URL="http://gofr-vault:${GOFR_VAULT_PORT:-8200}"
if [[ -z "${!VAULT_URL_VAR:-}" ]]; then
    export "${VAULT_URL_VAR}"="${DEFAULT_VAULT_URL}"
fi

# Vault token - use GOFR_VAULT_DEV_TOKEN from gofr_ports.sh if available
DEFAULT_VAULT_TOKEN="${GOFR_VAULT_DEV_TOKEN:-gofr-dev-root-token}"
if [[ -z "${!VAULT_TOKEN_VAR:-}" ]]; then
    export "${VAULT_TOKEN_VAR}"="${DEFAULT_VAULT_TOKEN}"
fi

# Auth backend - default to vault
if [[ -z "${!AUTH_BACKEND_VAR:-}" ]]; then
    export "${AUTH_BACKEND_VAR}"="vault"
fi

# Vault path prefix (e.g., gofr-iq/auth for GOFR)
if [[ -z "${!VAULT_PATH_PREFIX_VAR:-}" ]]; then
    PATH_PREFIX=$(echo "${PREFIX}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
    export "${VAULT_PATH_PREFIX_VAR}"="${PATH_PREFIX}/auth"
fi

# Vault mount point - default to secret
if [[ -z "${!VAULT_MOUNT_POINT_VAR:-}" ]]; then
    export "${VAULT_MOUNT_POINT_VAR}"="secret"
fi

# JWT secret - generate if not set
JWT_SECRET_VAR="${PREFIX}_JWT_SECRET"
if [[ -z "${!JWT_SECRET_VAR:-}" ]]; then
    # Generate secure random secret
    JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
    export "${JWT_SECRET_VAR}"="${JWT_SECRET}"
    echo "[INFO] Generated JWT secret: ${JWT_SECRET:0:16}..." >&2
fi

# Log configuration (to stderr)
echo "=== GOFR Auth Bootstrap ===" >&2
echo "Prefix:       ${PREFIX}" >&2
echo "Backend:      ${!AUTH_BACKEND_VAR:-vault}" >&2
echo "Vault URL:    ${!VAULT_URL_VAR:-not set}" >&2
echo "Vault Token:  ${!VAULT_TOKEN_VAR:0:16}..." >&2
echo "" >&2

# Run the Python bootstrap script
# Tokens go to stdout, logs go to stderr
cd "${GOFR_COMMON_ROOT}"

# Use uv run if available, otherwise try python3 directly
if command -v uv &> /dev/null; then
    uv run python3 "${SCRIPT_DIR}/bootstrap_auth.py" --prefix "${PREFIX}" "${EXTRA_ARGS[@]}"
elif [[ -f "${GOFR_COMMON_ROOT}/.venv/bin/python" ]]; then
    "${GOFR_COMMON_ROOT}/.venv/bin/python" "${SCRIPT_DIR}/bootstrap_auth.py" --prefix "${PREFIX}" "${EXTRA_ARGS[@]}"
else
    python3 "${SCRIPT_DIR}/bootstrap_auth.py" --prefix "${PREFIX}" "${EXTRA_ARGS[@]}"
fi

exit_code=$?

if [[ $exit_code -eq 0 ]]; then
    echo "" >&2
    echo "✓ Bootstrap complete" >&2
else
    echo "" >&2
    echo "✗ Bootstrap failed (exit code: ${exit_code})" >&2
fi

exit $exit_code
