#!/bin/sh
set -e

echo "Initialising custom n8n nodes..."

# Ensure the nodes directory exists
mkdir -p /home/node/.n8n/nodes

# Copy the pre-installed nodes from the image to the volume
if [ -d "/opt/custom-nodes/node_modules/n8n-nodes-openrouter" ]; then
    echo "Installing n8n-nodes-openrouter..."
    # Remove old version if exists
    rm -rf /home/node/.n8n/nodes/n8n-nodes-openrouter
    # Copy fresh from image
    cp -r /opt/custom-nodes/node_modules/n8n-nodes-openrouter /home/node/.n8n/nodes/
    
    # Verify installation
    if [ -f "/home/node/.n8n/nodes/n8n-nodes-openrouter/package.json" ]; then
        echo "OpenRouter node installed successfully"
        ls -la /home/node/.n8n/nodes/n8n-nodes-openrouter/dist/ 2>/dev/null || echo "Warning: dist directory not found"
    else
        echo "Error: Installation verification failed"
    fi
else
    echo "Warning: n8n-nodes-openrouter not found in /opt/custom-nodes"
fi

echo "Starting n8n..."

# Fix argument passing: if the command starts with 'n8n', strip it
# because /docker-entrypoint.sh prepends 'n8n' to arguments.
if [ "$1" = "n8n" ]; then
    shift
fi

# Hand off to the original entrypoint
exec /docker-entrypoint.sh "$@"
