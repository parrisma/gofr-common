#!/bin/bash
# =======================================================================
# GOFR Infrastructure Stop All
# Stops Neo4j and ChromaDB services
# =======================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================================================="
echo "Stopping GOFR Infrastructure"
echo "======================================================================="

cd "${SCRIPT_DIR}"

docker compose -f docker-compose.infra.yml down

echo ""
echo "======================================================================="
echo "Infrastructure Stopped"
echo "======================================================================="
echo ""
echo "Note: Volumes preserved. Use 'docker compose down -v' to remove data."
echo "======================================================================="
