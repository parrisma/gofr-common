#!/bin/bash
# =======================================================================
# GOFR Infrastructure Start All
# Starts Neo4j and ChromaDB services
# =======================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================================================="
echo "Starting GOFR Infrastructure"
echo "======================================================================="

cd "${SCRIPT_DIR}"

# Use docker compose
docker compose -f docker-compose.infra.yml up -d

echo ""
echo "======================================================================="
echo "Infrastructure Started"
echo "======================================================================="
echo ""
echo "Services:"
echo "  Neo4j Browser:  http://localhost:${NEO4J_HTTP_PORT:-7474}"
echo "  Neo4j Bolt:     bolt://localhost:${NEO4J_BOLT_PORT:-7687}"
echo "  ChromaDB:       http://localhost:${CHROMA_PORT:-8000}"
echo ""
echo "From GOFR containers (on gofr-net network):"
echo "  Neo4j:   bolt://gofr-neo4j:7687"
echo "  Chroma:  http://gofr-chroma:8000"
echo ""
echo "To stop: ./stop-all.sh"
echo "======================================================================="
