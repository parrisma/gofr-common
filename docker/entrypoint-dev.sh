#!/bin/bash
set -e

# Standard GOFR user paths - all projects use 'gofr' user
GOFR_USER="gofr"
PROJECT_DIR="/home/${GOFR_USER}/devroot/gofr-common"
VENV_DIR="$PROJECT_DIR/.venv"

echo "======================================================================="
echo "GOFR-Common Container Entrypoint"
echo "======================================================================="

# Fix data directory permissions if mounted as volume
if [ -d "$PROJECT_DIR/data" ]; then
    if [ ! -w "$PROJECT_DIR/data" ]; then
        echo "Fixing permissions for $PROJECT_DIR/data..."
        sudo chown -R ${GOFR_USER}:${GOFR_USER} "$PROJECT_DIR/data" 2>/dev/null || \
            echo "Warning: Could not fix permissions. Run container with --user $(id -u):$(id -g)"
    fi
fi

# Create subdirectories if they don't exist
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/logs"

# Ensure virtual environment exists and is valid
if [ ! -f "$VENV_DIR/bin/python" ] || [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "Creating Python virtual environment..."
    cd "$PROJECT_DIR"
    UV_VENV_CLEAR=1 uv venv "$VENV_DIR" --python=python3.11
    echo "Virtual environment created at $VENV_DIR"
fi

# Activate venv for subsequent commands
source "$VENV_DIR/bin/activate"

# Install gofr-common as editable package with all optional deps
if [ -f "$PROJECT_DIR/pyproject.toml" ]; then
    echo "Installing gofr-common (editable) with all optional dependencies..."
    cd "$PROJECT_DIR"
    uv pip install -e ".[all]" || echo "Warning: Could not install all optional dependencies"
fi

# Show installed packages
echo ""
echo "Environment ready. Installed packages:"
uv pip list

echo ""
echo "======================================================================="
echo "Entrypoint complete. Executing: $@"
echo "======================================================================="

exec "$@"
