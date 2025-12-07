#!/bin/bash
# Test runner script for gofr-common
# This script runs pytest with proper configuration
#
# Usage:
#   ./scripts/run_tests.sh                          # Run all tests
#   ./scripts/run_tests.sh tests/test_config.py    # Run specific test file
#   ./scripts/run_tests.sh -k "auth"               # Run tests matching keyword
#   ./scripts/run_tests.sh -v                      # Run with verbose output
#   ./scripts/run_tests.sh --cov                   # Run with coverage report
#   ./scripts/run_tests.sh --docker                # Run tests in Docker container

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
USE_DOCKER=false
COVERAGE=false
PYTEST_ARGS=()

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --docker)
            USE_DOCKER=true
            shift
            ;;
        --cov|--coverage)
            COVERAGE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS] [PYTEST_ARGS...]"
            echo ""
            echo "Options:"
            echo "  --docker      Run tests inside Docker container"
            echo "  --cov         Run with coverage report"
            echo "  --help, -h    Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                              # Run all tests"
            echo "  $0 tests/test_config.py        # Run specific test file"
            echo "  $0 -k 'auth'                   # Run tests matching keyword"
            echo "  $0 -v                          # Run with verbose output"
            echo "  $0 --cov                       # Run with coverage"
            echo "  $0 --docker                    # Run in Docker"
            echo "  $0 --docker -v                 # Run in Docker, verbose"
            exit 0
            ;;
        *)
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

echo -e "${GREEN}=== GOFR-Common Test Runner ===${NC}"
echo "Project root: ${PROJECT_ROOT}"
echo ""

# Build pytest command
PYTEST_CMD="pytest"

# Add coverage if requested
if [[ "$COVERAGE" == "true" ]]; then
    PYTEST_CMD="$PYTEST_CMD --cov=gofr_common --cov-report=term-missing --cov-report=html"
fi

# Add default test directory if no args provided
if [[ ${#PYTEST_ARGS[@]} -eq 0 ]]; then
    PYTEST_ARGS=("tests/")
fi

# Add verbose by default for better output
if [[ ! " ${PYTEST_ARGS[*]} " =~ " -v " ]] && [[ ! " ${PYTEST_ARGS[*]} " =~ " -q " ]]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

# Construct full command
FULL_CMD="$PYTEST_CMD ${PYTEST_ARGS[*]}"

if [[ "$USE_DOCKER" == "true" ]]; then
    # Run in Docker container
    CONTAINER_NAME="gofr-common-dev"
    
    # Check if container is running
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "${YELLOW}Container ${CONTAINER_NAME} is not running.${NC}"
        echo -e "${YELLOW}Starting container...${NC}"
        
        # Try to start existing stopped container
        if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            docker start "${CONTAINER_NAME}"
            sleep 2
        else
            echo -e "${RED}Container ${CONTAINER_NAME} does not exist.${NC}"
            echo "Run: ./docker/run-dev.sh to create it"
            exit 1
        fi
    fi
    
    echo -e "${BLUE}Running tests in Docker container: ${CONTAINER_NAME}${NC}"
    echo "Command: $FULL_CMD"
    echo ""
    
    docker exec "${CONTAINER_NAME}" bash -c "source .venv/bin/activate && $FULL_CMD"
    EXIT_CODE=$?
else
    # Run locally
    echo -e "${BLUE}Running tests locally${NC}"
    echo "Command: $FULL_CMD"
    echo ""
    
    # Check if we're in a virtual environment
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        if [[ -f ".venv/bin/activate" ]]; then
            echo -e "${YELLOW}Activating virtual environment...${NC}"
            source .venv/bin/activate
        else
            echo -e "${YELLOW}No virtual environment found. Running with system Python.${NC}"
        fi
    fi
    
    # Run pytest
    eval "$FULL_CMD"
    EXIT_CODE=$?
fi

echo ""
if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}=== All tests passed! ===${NC}"
else
    echo -e "${RED}=== Some tests failed (exit code: $EXIT_CODE) ===${NC}"
fi

exit $EXIT_CODE
