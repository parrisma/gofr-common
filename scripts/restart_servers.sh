#!/bin/bash
# Shared GOFR Server Restart Script
# Restarts all servers in correct order: MCP → MCPO → Web
#
# This script is called from project-specific wrappers that set environment variables.
#
# Required environment variables:
#   GOFR_PROJECT_NAME    - Project name for display (e.g., "gofr-np", "gofr-dig")
#   GOFR_PROJECT_ROOT    - Project root directory
#   GOFR_LOGS_DIR        - Log directory for output files
#   GOFR_DATA_DIR        - Data directory (for display)
#   GOFR_ENV             - Environment: PROD or TEST
#   GOFR_MCP_PORT        - MCP server port
#   GOFR_MCPO_PORT       - MCPO wrapper port
#   GOFR_WEB_PORT        - Web server port
#
# Optional environment variables:
#   GOFR_MCP_HOST        - MCP server bind host (default: 0.0.0.0)
#   GOFR_MCPO_HOST       - MCPO wrapper bind host (default: 0.0.0.0)
#   GOFR_WEB_HOST        - Web server bind host (default: 0.0.0.0)
#   GOFR_NETWORK         - Network name (for display)
#   GOFR_MCP_EXTRA_ARGS  - Extra args for MCP server
#   GOFR_MCPO_EXTRA_ARGS - Extra args for MCPO wrapper
#   GOFR_WEB_EXTRA_ARGS  - Extra args for Web server
#
# Usage from project wrapper:
#   export GOFR_PROJECT_NAME="gofr-np"
#   export GOFR_PROJECT_ROOT="/path/to/gofr-np"
#   # ... set other vars ...
#   source /path/to/gofr-common/scripts/restart_servers.sh "$@"

set -e

# Validate required environment variables
required_vars=(
    "GOFR_PROJECT_NAME"
    "GOFR_PROJECT_ROOT"
    "GOFR_LOGS_DIR"
    "GOFR_DATA_DIR"
    "GOFR_ENV"
    "GOFR_MCP_PORT"
    "GOFR_MCPO_PORT"
    "GOFR_WEB_PORT"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "ERROR: Required environment variable $var is not set"
        exit 1
    fi
done

# Default hosts
GOFR_MCP_HOST="${GOFR_MCP_HOST:-0.0.0.0}"
GOFR_MCPO_HOST="${GOFR_MCPO_HOST:-0.0.0.0}"
GOFR_WEB_HOST="${GOFR_WEB_HOST:-0.0.0.0}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Parse command line arguments
KILL_ALL=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --kill-all)
            KILL_ALL=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "OPTIONS:"
            echo "    --kill-all    Stop all servers without restarting"
            echo "    --help        Show this help message"
            echo ""
            echo "Environment variables should be set by the project wrapper script."
            exit 0
            ;;
        *)
            # Unknown options are ignored (may be handled by wrapper)
            shift
            ;;
    esac
done

echo "======================================================================="
echo "$GOFR_PROJECT_NAME Server Restart Script"
echo "Environment: $GOFR_ENV"
echo "Data Root: $GOFR_DATA_DIR"
if [ -n "$GOFR_NETWORK" ]; then
    echo "Network: $GOFR_NETWORK"
fi
echo "======================================================================="

# Function to kill process and wait for it to die
kill_and_wait() {
    local pattern=$1
    local name=$2
    local pids=$(pgrep -f "$pattern" 2>/dev/null || echo "")
    
    if [ -z "$pids" ]; then
        echo "  - No $name running"
        return 0
    fi
    
    echo "  Killing $name (PIDs: $pids)..."
    pkill -9 -f "$pattern" 2>/dev/null || true
    
    # Wait for processes to die (max 10 seconds)
    for i in {1..20}; do
        if ! pgrep -f "$pattern" >/dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $name stopped"
            return 0
        fi
        sleep 0.5
    done
    
    echo -e "  ${YELLOW}⚠${NC} Warning: $name may still be running"
    return 1
}

# Function to verify server is responding
verify_server() {
    local port=$1
    local name=$2
    local endpoint=$3
    local max_attempts=${4:-30}
    local attempt=0
    
    echo "  Waiting for $name to be ready..."
    while [ $attempt -lt $max_attempts ]; do
        if curl -s -m 2 "http://localhost:${port}${endpoint}" >/dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $name ready on port $port"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    
    echo -e "  ${RED}✗${NC} $name NOT responding after ${max_attempts}s"
    return 1
}

# Kill existing processes
echo ""
echo "Step 1: Stopping existing servers..."
echo "-----------------------------------------------------------------------"

# Kill servers in reverse order (Web, MCPO, MCP)
kill_and_wait "app.main_web" "Web server"
kill_and_wait "mcpo --port\|mcpo" "MCPO wrapper"
kill_and_wait "app.main_mcpo" "MCPO wrapper process"
kill_and_wait "app.main_mcp" "MCP server"

# Wait for ports to be released
echo ""
echo "Waiting for ports to be released..."
sleep 2

# Check if --kill-all flag is set
if [ "$KILL_ALL" = true ]; then
    echo ""
    echo "Kill-all mode: Exiting without restart"
    echo "======================================================================="
    exit 0
fi

# Create logs directory if it doesn't exist
mkdir -p "$GOFR_LOGS_DIR"

# Start MCP server
echo ""
echo "Step 2: Starting MCP server ($GOFR_MCP_HOST:$GOFR_MCP_PORT)..."
echo "-----------------------------------------------------------------------"

cd "$GOFR_PROJECT_ROOT"
nohup uv run python -m app.main_mcp \
    --no-auth \
    --host $GOFR_MCP_HOST \
    --port $GOFR_MCP_PORT \
    $GOFR_MCP_EXTRA_ARGS \
    > "$GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_mcp.log" 2>&1 &

MCP_PID=$!
echo "  MCP server starting (PID: $MCP_PID)"
echo "  Log: $GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_mcp.log"

# Verify MCP is operational
if ! verify_server $GOFR_MCP_PORT "MCP Server" "/mcp/"; then
    echo -e "${RED}ERROR: MCP server failed to start${NC}"
    tail -20 "$GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_mcp.log"
    exit 1
fi

# Start MCPO wrapper
echo ""
echo "Step 3: Starting MCPO wrapper ($GOFR_MCPO_HOST:$GOFR_MCPO_PORT)..."
echo "-----------------------------------------------------------------------"

nohup uv run mcpo --port $GOFR_MCPO_PORT --host $GOFR_MCPO_HOST \
    -- uv run python -m app.main_mcpo \
    --host $GOFR_MCP_HOST --port $GOFR_MCP_PORT \
    $GOFR_MCPO_EXTRA_ARGS \
    > "$GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_mcpo.log" 2>&1 &

MCPO_PID=$!
echo "  MCPO wrapper starting (PID: $MCPO_PID)"
echo "  Log: $GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_mcpo.log"

# Verify MCPO is operational
if ! verify_server $GOFR_MCPO_PORT "MCPO Wrapper" "/openapi.json" 15; then
    echo -e "${RED}ERROR: MCPO wrapper failed to start${NC}"
    tail -20 "$GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_mcpo.log"
    exit 1
fi

# Start Web server
echo ""
echo "Step 4: Starting Web server ($GOFR_WEB_HOST:$GOFR_WEB_PORT)..."
echo "-----------------------------------------------------------------------"

nohup uv run python -m app.main_web \
    --host $GOFR_WEB_HOST \
    --port $GOFR_WEB_PORT \
    $GOFR_WEB_EXTRA_ARGS \
    > "$GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_web.log" 2>&1 &

WEB_PID=$!
echo "  Web server starting (PID: $WEB_PID)"
echo "  Log: $GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_web.log"

# Verify Web server is operational
if ! verify_server $GOFR_WEB_PORT "Web Server" "/ping" 15; then
    echo -e "${RED}ERROR: Web server failed to start${NC}"
    tail -20 "$GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_web.log"
    exit 1
fi

# Summary
echo ""
echo "======================================================================="
echo -e "${GREEN}All servers started successfully!${NC}"
echo "======================================================================="
echo ""
echo "Server URLs:"
echo "  MCP:  http://localhost:$GOFR_MCP_PORT/mcp/"
echo "  MCPO: http://localhost:$GOFR_MCPO_PORT/openapi.json"
echo "  Web:  http://localhost:$GOFR_WEB_PORT/"
echo ""
echo "Logs:"
echo "  MCP:  $GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_mcp.log"
echo "  MCPO: $GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_mcpo.log"
echo "  Web:  $GOFR_LOGS_DIR/${GOFR_PROJECT_NAME}_web.log"
echo ""
