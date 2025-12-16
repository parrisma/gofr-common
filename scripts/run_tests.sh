#!/bin/bash
# =============================================================================
# GOFR-Common Test Runner
# =============================================================================
# Standardized test runner script with consistent configuration across all
# GOFR projects. This script:
# - Sets up virtual environment
# - Configures PYTHONPATH for gofr-common discovery
# - Supports coverage reporting
# - Supports Docker execution
# - Runs pytest with proper configuration
#
# Usage:
#   ./scripts/run_tests.sh                          # Run all tests
#   ./scripts/run_tests.sh tests/test_config.py    # Run specific test file
#   ./scripts/run_tests.sh -k "auth"               # Run tests matching keyword
#   ./scripts/run_tests.sh -v                      # Run with verbose output
#   ./scripts/run_tests.sh --coverage              # Run with coverage report
#   ./scripts/run_tests.sh --coverage-html         # Run with HTML coverage report
#   ./scripts/run_tests.sh --docker                # Run tests in Docker container
#   ./scripts/run_tests.sh --unit                  # Run unit tests only
#   ./scripts/run_tests.sh --cleanup-only          # Clean environment only
# =============================================================================

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# =============================================================================
# CONFIGURATION
# =============================================================================

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

# Project-specific configuration
PROJECT_NAME="gofr-common"
ENV_PREFIX="GOFR_COMMON"
CONTAINER_NAME="gofr-common-dev"
TEST_DIR="tests"
COVERAGE_SOURCE="gofr_common"

# Activate virtual environment
VENV_DIR="${PROJECT_ROOT}/.venv"
if [ -f "${VENV_DIR}/bin/activate" ]; then
    source "${VENV_DIR}/bin/activate"
    echo "Activated venv: ${VENV_DIR}"
else
    echo -e "${YELLOW}Warning: Virtual environment not found at ${VENV_DIR}${NC}"
    echo "Trying to use uv run instead..."
fi

# Set up PYTHONPATH for module discovery
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

# Test configuration
export GOFR_COMMON_ENV="TEST"
export GOFR_COMMON_JWT_SECRET="test-secret-key-for-secure-testing-do-not-use-in-production"
export GOFR_COMMON_LOG_LEVEL="DEBUG"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

print_header() {
    echo -e "${GREEN}=== ${PROJECT_NAME} Test Runner ===${NC}"
    echo "Project root: ${PROJECT_ROOT}"
    echo "Environment: ${GOFR_COMMON_ENV}"
    echo "PYTHONPATH: ${PYTHONPATH}"
    echo ""
}

cleanup_environment() {
    echo -e "${YELLOW}Cleaning up test environment...${NC}"
    # Remove any test artifacts
    rm -rf "${PROJECT_ROOT}/.pytest_cache" 2>/dev/null || true
    rm -rf "${PROJECT_ROOT}/htmlcov" 2>/dev/null || true
    rm -f "${PROJECT_ROOT}/.coverage" 2>/dev/null || true
    echo -e "${GREEN}Cleanup complete${NC}"
}

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

USE_DOCKER=false
COVERAGE=false
COVERAGE_HTML=false
RUN_UNIT=false
CLEANUP_ONLY=false
SKIP_LINT=false
PYTEST_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --docker)
            USE_DOCKER=true
            shift
            ;;
        --coverage|--cov)
            COVERAGE=true
            shift
            ;;
        --coverage-html)
            COVERAGE=true
            COVERAGE_HTML=true
            shift
            ;;
        --unit)
            RUN_UNIT=true
            shift
            ;;
        --cleanup-only)
            CLEANUP_ONLY=true
            shift
            ;;
        --skip-lint|--no-lint)
            SKIP_LINT=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS] [PYTEST_ARGS...]"
            echo ""
            echo "Options:"
            echo "  --docker         Run tests inside Docker container"
            echo "  --coverage       Run with coverage report"
            echo "  --coverage-html  Run with HTML coverage report"
            echo "  --unit           Run unit tests only"
            echo "  --skip-lint      Skip code quality checks (ruff)"
            echo "  --cleanup-only   Clean environment and exit"
            echo "  --help, -h       Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                              # Run all tests"
            echo "  $0 tests/test_config.py        # Run specific test file"
            echo "  $0 -k 'auth'                   # Run tests matching keyword"
            echo "  $0 -v                          # Run with verbose output"
            echo "  $0 --coverage                  # Run with coverage"
            echo "  $0 --docker                    # Run in Docker"
            echo "  $0 --skip-lint                 # Skip linting, run tests only"
            exit 0
            ;;
        *)
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# =============================================================================
# MAIN EXECUTION
# =============================================================================

print_header

# Handle cleanup-only mode
if [ "$CLEANUP_ONLY" = true ]; then
    cleanup_environment
    exit 0
fi

# =============================================================================
# CODE QUALITY CHECKS (RUFF)
# =============================================================================

if [ "$SKIP_LINT" = false ]; then
    echo -e "${BLUE}Running code quality checks (ruff)...${NC}"
    
    RUFF_CMD="ruff check src/ tests/"
    
    if [ "$USE_DOCKER" = true ]; then
        if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            echo -e "${RED}Container ${CONTAINER_NAME} is not running for lint check.${NC}"
            exit 1
        fi
        docker exec "${CONTAINER_NAME}" bash -c "cd /home/${PROJECT_NAME} && source .venv/bin/activate && ${RUFF_CMD}"
        LINT_EXIT_CODE=$?
    else
        if command -v ruff &> /dev/null; then
            ${RUFF_CMD}
            LINT_EXIT_CODE=$?
        elif command -v uv &> /dev/null; then
            uv run ${RUFF_CMD}
            LINT_EXIT_CODE=$?
        else
            echo -e "${YELLOW}Warning: ruff not found, skipping lint checks${NC}"
            LINT_EXIT_CODE=0
        fi
    fi
    
    if [ $LINT_EXIT_CODE -ne 0 ]; then
        echo ""
        echo -e "${RED}=== Code quality checks failed! ===${NC}"
        echo -e "${YELLOW}Fix issues with: ruff check src/ tests/ --fix${NC}"
        echo -e "${YELLOW}Or skip lint with: $0 --skip-lint${NC}"
        exit $LINT_EXIT_CODE
    fi
    
    echo -e "${GREEN}Code quality checks passed!${NC}"
    echo ""
fi

# =============================================================================
# PYTEST EXECUTION
# =============================================================================

# Build pytest command
PYTEST_CMD="pytest"

# Add coverage if requested
COVERAGE_ARGS=""
if [ "$COVERAGE" = true ]; then
    COVERAGE_ARGS="--cov=${COVERAGE_SOURCE} --cov-report=term-missing"
    if [ "$COVERAGE_HTML" = true ]; then
        COVERAGE_ARGS="${COVERAGE_ARGS} --cov-report=html:htmlcov"
    fi
    echo -e "${BLUE}Coverage reporting enabled${NC}"
fi

# Add default test directory if no args provided
if [ ${#PYTEST_ARGS[@]} -eq 0 ]; then
    PYTEST_ARGS=("${TEST_DIR}/")
fi

# Add verbose by default if not specified
if [[ ! " ${PYTEST_ARGS[*]} " =~ " -v " ]] && [[ ! " ${PYTEST_ARGS[*]} " =~ " -q " ]]; then
    PYTEST_CMD="${PYTEST_CMD} -v"
fi

# Construct full command
FULL_CMD="${PYTEST_CMD} ${PYTEST_ARGS[*]} ${COVERAGE_ARGS}"

# =============================================================================
# EXECUTION
# =============================================================================

if [ "$USE_DOCKER" = true ]; then
    # Run in Docker container
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "${YELLOW}Container ${CONTAINER_NAME} is not running.${NC}"
        echo -e "${YELLOW}Starting container...${NC}"
        
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
    echo "Command: ${FULL_CMD}"
    echo ""
    
    docker exec "${CONTAINER_NAME}" bash -c "cd /home/${PROJECT_NAME} && source .venv/bin/activate && ${FULL_CMD}"
    EXIT_CODE=$?
else
    # Run locally
    echo -e "${BLUE}Running tests locally${NC}"
    echo "Command: ${FULL_CMD}"
    echo ""
    
    if command -v uv &> /dev/null; then
        uv run ${FULL_CMD}
    else
        eval "${FULL_CMD}"
    fi
    EXIT_CODE=$?
fi

# =============================================================================
# RESULTS
# =============================================================================

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}=== All tests passed! ===${NC}"
    if [ "$COVERAGE" = true ] && [ "$COVERAGE_HTML" = true ]; then
        echo -e "${BLUE}HTML coverage report: ${PROJECT_ROOT}/htmlcov/index.html${NC}"
    fi
else
    echo -e "${RED}=== Some tests failed (exit code: ${EXIT_CODE}) ===${NC}"
fi

exit $EXIT_CODE
