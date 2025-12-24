#!/bin/bash
set -e

# Standard GOFR user paths - all projects use 'gofr' user
GOFR_USER="gofr"
PROJECT_DIR="/home/${GOFR_USER}/devroot/gofr-common"
VENV_DIR="$PROJECT_DIR/.venv"

echo "======================================================================="
echo "GOFR-Common Container Entrypoint"
echo "======================================================================="

# Fix Docker socket permissions if mounted
# This allows the gofr user to run docker commands (sibling containers)
if [ -S /var/run/docker.sock ]; then
    DOCKER_SOCK_GID=$(stat -c '%g' /var/run/docker.sock)
    echo "Docker socket detected (GID: $DOCKER_SOCK_GID)"
    
    # Adjust docker group GID to match host's socket GID
    if [ "$DOCKER_SOCK_GID" != "0" ]; then
        # Check if docker group exists with different GID
        CURRENT_DOCKER_GID=$(getent group docker | cut -d: -f3 || echo "")
        if [ -n "$CURRENT_DOCKER_GID" ] && [ "$CURRENT_DOCKER_GID" != "$DOCKER_SOCK_GID" ]; then
            echo "Adjusting docker group GID from $CURRENT_DOCKER_GID to $DOCKER_SOCK_GID..."
            sudo groupmod -g "$DOCKER_SOCK_GID" docker 2>/dev/null || true
        elif [ -z "$CURRENT_DOCKER_GID" ]; then
            echo "Creating docker group with GID $DOCKER_SOCK_GID..."
            sudo groupadd -g "$DOCKER_SOCK_GID" docker 2>/dev/null || true
        fi
        
        # Add gofr user to docker group if not already
        if ! groups ${GOFR_USER} | grep -q docker; then
            echo "Adding ${GOFR_USER} to docker group..."
            sudo usermod -aG docker ${GOFR_USER} 2>/dev/null || true
        fi
    else
        # Socket is owned by root (GID 0), make it accessible
        echo "Docker socket owned by root, setting permissions..."
        sudo chmod 666 /var/run/docker.sock 2>/dev/null || true
    fi
    
    # Verify docker access
    if docker info >/dev/null 2>&1; then
        echo "Docker access: OK"
    else
        echo "Warning: Docker access not available (may need container restart)"
    fi
fi

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
