# GOFR Project Migration Guide

This guide documents the steps to migrate a GOFR project to use the shared `gofr-common` infrastructure via git submodule.

## Prerequisites

- `gofr-base:latest` Docker image built (from `gofr-common/docker/`)
- `gofr-common` repository pushed to GitHub

## Migration Steps

### Step 1: Add gofr-common as Git Submodule

```bash
cd /home/parris3142/devroot/<project-name>

# Add the submodule (use relative path for same parent directory)
git submodule add -f ../gofr-common lib/gofr-common

# Verify submodule was added
cat .gitmodules
ls -la lib/gofr-common/
```

### Step 2: Update .gitignore

Add exception for the submodule if `lib/` is ignored:

```bash
# Edit .gitignore and add:
!lib/gofr-common
```

### Step 3: Update pyproject.toml

1. **Remove gofr-common from dependencies** (entrypoint handles installation):

```toml
[project]
# ...
# Note: gofr-common is installed as editable from lib/gofr-common submodule by entrypoint
dependencies = [
    # Remove: "gofr-common @ file:lib/gofr-common",
    # Keep other dependencies...
]
```

2. **Add hatch direct references setting** (if keeping gofr-common in dependencies):

```toml
[tool.hatch.metadata]
allow-direct-references = true
```

### Step 4: Create/Update Dockerfile.dev

Create `docker/Dockerfile.dev` that extends the shared base image:

```dockerfile
# GOFR-<PROJECT> Development Image
# Extends gofr-base:latest with project-specific dev tools
FROM gofr-base:latest

# Install additional dev tools
RUN apt-get update && apt-get install -y \
    gh \
    openssh-server \
    dnsutils \
    net-tools \
    netcat-openbsd \
    telnet \
    lsof \
    htop \
    strace \
    tcpdump \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Create project directories
RUN mkdir -p /home/gofr/devroot/gofr-<project>/data \
    && mkdir -p /home/gofr/devroot/gofr-common \
    && chown -R gofr:gofr /home/gofr/devroot

# Copy entrypoint
COPY docker/entrypoint-dev.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /home/gofr/devroot/gofr-<project>

# SSH config for git operations
RUN mkdir -p /home/gofr/.ssh && chmod 700 /home/gofr/.ssh

# Create venv (will be populated by entrypoint)
RUN uv venv /home/gofr/devroot/gofr-<project>/.venv --python=python3.11

# Standard GOFR ports
EXPOSE 8020 8021 8022

USER gofr
ENTRYPOINT ["/entrypoint.sh"]
CMD ["tail", "-f", "/dev/null"]
```

### Step 5: Create/Update entrypoint-dev.sh

Create `docker/entrypoint-dev.sh`:

```bash
#!/bin/bash
set -e

# Standard GOFR user paths - all projects use 'gofr' user
GOFR_USER="gofr"
PROJECT_DIR="/home/${GOFR_USER}/devroot/gofr-<project>"
# gofr-common is now a git submodule in lib/gofr-common
COMMON_DIR="$PROJECT_DIR/lib/gofr-common"
VENV_DIR="$PROJECT_DIR/.venv"

echo "======================================================================="
echo "GOFR-<PROJECT> Container Entrypoint"
echo "======================================================================="

# Fix data directory permissions if mounted as volume
if [ -d "$PROJECT_DIR/data" ]; then
    if [ ! -w "$PROJECT_DIR/data" ]; then
        echo "Fixing permissions for $PROJECT_DIR/data..."
        sudo chown -R ${GOFR_USER}:${GOFR_USER} "$PROJECT_DIR/data" 2>/dev/null || \
            echo "Warning: Could not fix permissions. Run container with --user $(id -u):$(id -g)"
    fi
fi

# Ensure virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment..."
    uv venv "$VENV_DIR" --python=python3.11
    echo "Virtual environment created at $VENV_DIR"
fi

# Install gofr-common as editable package
if [ -d "$COMMON_DIR" ]; then
    echo "Installing gofr-common (editable)..."
    cd "$PROJECT_DIR"
    uv pip install -e "$COMMON_DIR"
else
    echo "Warning: gofr-common not found at $COMMON_DIR"
    echo "Make sure the submodule is initialized: git submodule update --init"
fi

# Install project dependencies
if [ -f "$PROJECT_DIR/pyproject.toml" ]; then
    echo "Installing project dependencies from pyproject.toml..."
    cd "$PROJECT_DIR"
    uv pip install -e . || echo "Warning: Could not install project dependencies"
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
```

### Step 6: Create/Update build-dev.sh

Create `docker/build-dev.sh`:

```bash
#!/bin/bash
# Build GOFR-<PROJECT> development image
# Requires gofr-base:latest to be built first

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Get user's UID/GID for permission matching
USER_UID=$(id -u)
USER_GID=$(id -g)

echo "======================================================================="
echo "Building GOFR-<PROJECT> Development Image"
echo "======================================================================="
echo "User UID: $USER_UID"
echo "User GID: $USER_GID"
echo "======================================================================="

# Check if base image exists
if ! docker image inspect gofr-base:latest >/dev/null 2>&1; then
    echo "Error: gofr-base:latest not found. Build it first:"
    echo "  cd ../gofr-common/docker && ./build-base.sh"
    exit 1
fi

echo ""
echo "Building gofr-<project>-dev:latest..."
docker build \
    -f "$SCRIPT_DIR/Dockerfile.dev" \
    -t gofr-<project>-dev:latest \
    "$PROJECT_ROOT"

echo ""
echo "======================================================================="
echo "Build complete: gofr-<project>-dev:latest"
echo "======================================================================="
echo ""
echo "Image size:"
docker images gofr-<project>-dev:latest --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

### Step 7: Create/Update run-dev.sh

Create `docker/run-dev.sh`:

```bash
#!/bin/bash
# Run GOFR-<PROJECT> development container
# Uses gofr-<project>-dev:latest image (built from gofr-base:latest)
# Standard user: gofr (UID 1000, GID 1000)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# gofr-common is now a git submodule at lib/gofr-common, no separate mount needed

# Standard GOFR user - all projects use same user
GOFR_USER="gofr"
GOFR_UID=1000
GOFR_GID=1000

# Container and image names
CONTAINER_NAME="gofr-<project>-dev"
IMAGE_NAME="gofr-<project>-dev:latest"

# Defaults from environment or hardcoded (adjust ports per project)
MCP_PORT="${GOFR<PROJECT>_MCP_PORT:-8020}"
MCPO_PORT="${GOFR<PROJECT>_MCPO_PORT:-8021}"
WEB_PORT="${GOFR<PROJECT>_WEB_PORT:-8022}"
DOCKER_NETWORK="${GOFR<PROJECT>_DOCKER_NETWORK:-gofr-net}"

echo "======================================================================="
echo "Starting GOFR-<PROJECT> Development Container"
echo "======================================================================="
echo "User: ${GOFR_USER} (UID=${GOFR_UID}, GID=${GOFR_GID})"
echo "Ports: MCP=$MCP_PORT, MCPO=$MCPO_PORT, Web=$WEB_PORT"
echo "Network: $DOCKER_NETWORK"
echo "======================================================================="

# Create docker network if it doesn't exist
if ! docker network inspect $DOCKER_NETWORK >/dev/null 2>&1; then
    echo "Creating network: $DOCKER_NETWORK"
    docker network create $DOCKER_NETWORK
fi

# Create docker volume for persistent data
VOLUME_NAME="gofr-<project>-data-dev"
if ! docker volume inspect $VOLUME_NAME >/dev/null 2>&1; then
    echo "Creating volume: $VOLUME_NAME"
    docker volume create $VOLUME_NAME
fi

# Stop and remove existing container
echo "Stopping existing container..."
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

echo ""
echo "Starting container..."
echo "  Source mount: $PROJECT_ROOT → /home/${GOFR_USER}/devroot/gofr-<project>"
echo "  (gofr-common included as submodule at lib/gofr-common)"

docker run -d \
    --name $CONTAINER_NAME \
    --network $DOCKER_NETWORK \
    --user ${GOFR_UID}:${GOFR_GID} \
    -v "$PROJECT_ROOT":/home/${GOFR_USER}/devroot/gofr-<project> \
    -v "$HOME/.ssh:/home/${GOFR_USER}/.ssh:ro" \
    -v $VOLUME_NAME:/home/${GOFR_USER}/devroot/gofr-<project>/data \
    -p 0.0.0.0:$MCP_PORT:8020 \
    -p 0.0.0.0:$MCPO_PORT:8021 \
    -p 0.0.0.0:$WEB_PORT:8022 \
    $IMAGE_NAME

if docker ps -q -f name=$CONTAINER_NAME | grep -q .; then
    echo ""
    echo "Container $CONTAINER_NAME is running"
fi

echo ""
echo "======================================================================="
echo "Development Container Ready"
echo "======================================================================="
echo ""
echo "Shell access:"
echo "  docker exec -it $CONTAINER_NAME /bin/bash"
echo ""
echo "Endpoints (from host):"
echo "  MCP Server:  http://localhost:$MCP_PORT/mcp"
echo "  MCPO Proxy:  http://localhost:$MCPO_PORT"
echo "  Web Server:  http://localhost:$WEB_PORT"
echo ""
echo "======================================================================="
```

### Step 8: Clean Up Duplicate Files

Remove files that are now in gofr-common:

```bash
cd /home/parris3142/devroot/<project-name>/docker

# Remove base image files (now in lib/gofr-common/docker/)
rm -f Dockerfile.base build-base.sh

# Remove backup files
rm -f *.bak
```

### Step 9: Build and Test

```bash
cd /home/parris3142/devroot/<project-name>

# Ensure base image exists
docker images gofr-base:latest

# Build project dev image (with --no-cache first time)
cd docker && docker build --no-cache -f Dockerfile.dev -t gofr-<project>-dev:latest ..

# Or use the build script
./docker/build-dev.sh

# Run the container
./docker/run-dev.sh

# Verify gofr-common is working
docker exec gofr-<project>-dev bash -c 'cd /home/gofr/devroot/gofr-<project> && source .venv/bin/activate && python -c "import gofr_common; print(\"SUCCESS\")"'
```

### Step 10: Commit Changes

```bash
cd /home/parris3142/devroot/<project-name>

git add .gitmodules lib/gofr-common
git add docker/ pyproject.toml .gitignore
git commit -m "Migrate to gofr-common submodule infrastructure"
git push
```

---

## Port Assignments (Suggested)

To avoid conflicts when running multiple projects:

| Project   | MCP Port | MCPO Port | Web Port |
|-----------|----------|-----------|----------|
| gofr-np   | 8020     | 8021      | 8022     |
| gofr-dig  | 8030     | 8031      | 8032     |
| gofr-doc  | 8040     | 8041      | 8042     |
| gofr-plot | 8050     | 8051      | 8052     |

---

## Troubleshooting

### Submodule not initialized
```bash
git submodule update --init --recursive
```

### gofr-common import fails
```bash
# Check submodule is present
ls -la lib/gofr-common/

# Manually install in container
docker exec -it gofr-<project>-dev bash
cd /home/gofr/devroot/gofr-<project>
uv pip install -e ./lib/gofr-common
```

### Permission issues
```bash
# Run container with your UID/GID
docker run --user $(id -u):$(id -g) ...
```

### Cached Docker layers
```bash
# Force rebuild without cache
docker build --no-cache -f docker/Dockerfile.dev -t gofr-<project>-dev:latest .
```

---

## Summary of Changes per Project

| File | Action | Notes |
|------|--------|-------|
| `.gitmodules` | Create | Submodule reference |
| `lib/gofr-common/` | Add | Git submodule |
| `.gitignore` | Update | Add `!lib/gofr-common` |
| `pyproject.toml` | Update | Remove/comment gofr-common dep |
| `docker/Dockerfile.dev` | Update | Use `FROM gofr-base:latest` |
| `docker/entrypoint-dev.sh` | Update | Use submodule path |
| `docker/build-dev.sh` | Update | Remove base image build |
| `docker/run-dev.sh` | Update | Remove gofr-common mount |
| `docker/Dockerfile.base` | Delete | Now in gofr-common |
| `docker/build-base.sh` | Delete | Now in gofr-common |
| `docker/*.bak` | Delete | Old backups |
