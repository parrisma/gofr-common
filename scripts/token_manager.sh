#!/bin/bash
# Shared GOFR Token Manager Wrapper Script
# Provides environment-aware access to JWT token management
#
# This script is called from project-specific wrappers that set environment variables.
#
# Required environment variables:
#   GOFR_PROJECT_NAME    - Project name for module path detection
#   GOFR_PROJECT_ROOT    - Project root directory
#   GOFR_TOKEN_STORE     - Path to token store JSON file
#   GOFR_ENV             - Environment: PROD or TEST
#   GOFR_ENV_VAR_PREFIX  - Environment variable prefix (e.g., "GOFR_NP", "GOFR_DIG")
#
# Optional environment variables:
#   GOFR_TOKEN_MODULE    - Python module path (default: app.auth.token_manager)
#
# Usage from project wrapper:
#   export GOFR_PROJECT_NAME="gofr-np"
#   export GOFR_PROJECT_ROOT="/path/to/gofr-np"
#   export GOFR_TOKEN_STORE="/path/to/tokens.json"
#   export GOFR_ENV="PROD"
#   export GOFR_ENV_VAR_PREFIX="GOFR_NP"
#   source /path/to/gofr-common/scripts/token_manager.sh "$@"
#
# Commands:
#   create    Create a new token
#   list      List all tokens
#   verify    Verify a token
#   revoke    Revoke a token
#
# Examples:
#   ./token_manager.sh create --group research --expires 3600
#   ./token_manager.sh list
#   ./token_manager.sh verify --token <token>
#   ./token_manager.sh revoke --token <token>

set -e

# Validate required environment variables
required_vars=(
    "GOFR_PROJECT_NAME"
    "GOFR_PROJECT_ROOT"
    "GOFR_TOKEN_STORE"
    "GOFR_ENV"
    "GOFR_ENV_VAR_PREFIX"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "ERROR: Required environment variable $var is not set"
        exit 1
    fi
done

# Default token module path
GOFR_TOKEN_MODULE="${GOFR_TOKEN_MODULE:-app.auth.token_manager}"

# Show help if requested
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "GOFR Token Manager - $GOFR_PROJECT_NAME"
    echo ""
    echo "Usage: $0 [--env PROD|TEST] <command> [options]"
    echo ""
    echo "Commands:"
    echo "    create    Create a new JWT token"
    echo "    list      List all active tokens"
    echo "    verify    Verify a token"
    echo "    revoke    Revoke a token"
    echo ""
    echo "Options:"
    echo "    --env ENV         Environment: PROD or TEST (default: $GOFR_ENV)"
    echo "    --group GROUP     Group name for token (create)"
    echo "    --expires SECS    Token expiry in seconds (create)"
    echo "    --token TOKEN     Token string (verify, revoke)"
    echo ""
    echo "Environment: $GOFR_ENV"
    echo "Token Store: $GOFR_TOKEN_STORE"
    exit 0
fi

# Build the environment-specific argument name
# Convert prefix like "GOFR_NP" to arg like "--gofr-np-env"
ENV_ARG_NAME=$(echo "$GOFR_ENV_VAR_PREFIX" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

# Run token manager with environment-specific paths
cd "$GOFR_PROJECT_ROOT"
exec uv run python -m "$GOFR_TOKEN_MODULE" \
    --${ENV_ARG_NAME}-env "$GOFR_ENV" \
    --token-store "$GOFR_TOKEN_STORE" \
    "$@"
