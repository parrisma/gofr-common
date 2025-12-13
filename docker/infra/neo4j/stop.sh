#!/bin/bash
# =======================================================================
# Neo4j Stop Script
# =======================================================================

CONTAINER_NAME="gofr-neo4j"

echo "Stopping ${CONTAINER_NAME}..."

if docker ps -q -f name=${CONTAINER_NAME} | grep -q .; then
    docker stop ${CONTAINER_NAME}
    echo "Container stopped"
else
    echo "Container not running"
fi

if [ "$1" = "--rm" ] || [ "$1" = "-r" ]; then
    docker rm ${CONTAINER_NAME} 2>/dev/null && echo "Container removed"
fi
