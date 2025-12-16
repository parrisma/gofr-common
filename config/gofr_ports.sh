#!/bin/bash
# =============================================================================
# GOFR Service Port Configuration
# =============================================================================
# Centralized port allocation for all GOFR services.
# Source this file to get standardized port definitions.
#
# Port Allocation Strategy:
# - Each service gets a base port in increments of 10
# - MCP (Model Context Protocol) = base + 0
# - MCPO (MCP Orchestrator) = base + 1
# - Web (Web UI/API) = base + 2
#
# This ensures:
# 1. Consistent port spacing across all services
# 2. Easy addition of new services
# 3. No port conflicts
# 4. Clear service identification by port range
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/gofr_ports.sh"
#   echo "GOFR-DOC MCP port: ${GOFR_DOC_MCP_PORT}"
# =============================================================================

# GOFR-DOC: Document generation service (8040-8042)
export GOFR_DOC_MCP_PORT="${GOFR_DOC_MCP_PORT:-8040}"
export GOFR_DOC_MCPO_PORT="${GOFR_DOC_MCPO_PORT:-8041}"
export GOFR_DOC_WEB_PORT="${GOFR_DOC_WEB_PORT:-8042}"

# GOFR-PLOT: Plotting and visualization service (8050-8052)
export GOFR_PLOT_MCP_PORT="${GOFR_PLOT_MCP_PORT:-8050}"
export GOFR_PLOT_MCPO_PORT="${GOFR_PLOT_MCPO_PORT:-8051}"
export GOFR_PLOT_WEB_PORT="${GOFR_PLOT_WEB_PORT:-8052}"

# GOFR-NP: Numerical Python service (8060-8062)
export GOFR_NP_MCP_PORT="${GOFR_NP_MCP_PORT:-8060}"
export GOFR_NP_MCPO_PORT="${GOFR_NP_MCPO_PORT:-8061}"
export GOFR_NP_WEB_PORT="${GOFR_NP_WEB_PORT:-8062}"

# GOFR-DIG: Data ingestion service (8070-8072)
export GOFR_DIG_MCP_PORT="${GOFR_DIG_MCP_PORT:-8070}"
export GOFR_DIG_MCPO_PORT="${GOFR_DIG_MCPO_PORT:-8071}"
export GOFR_DIG_WEB_PORT="${GOFR_DIG_WEB_PORT:-8072}"

# GOFR-IQ: Intelligence and query service (8080-8082)
export GOFR_IQ_MCP_PORT="${GOFR_IQ_MCP_PORT:-8080}"
export GOFR_IQ_MCPO_PORT="${GOFR_IQ_MCPO_PORT:-8081}"
export GOFR_IQ_WEB_PORT="${GOFR_IQ_WEB_PORT:-8082}"

# =============================================================================
# Infrastructure Services
# =============================================================================

# HashiCorp Vault: Secrets management (8201)
export GOFR_VAULT_PORT="${GOFR_VAULT_PORT:-8201}"
export GOFR_VAULT_DEV_TOKEN="${GOFR_VAULT_DEV_TOKEN:-gofr-dev-root-token}"

# ChromaDB: Vector database (8000)
export GOFR_CHROMA_PORT="${GOFR_CHROMA_PORT:-8000}"

# Neo4j: Graph database (7474 HTTP, 7687 Bolt)
export GOFR_NEO4J_HTTP_PORT="${GOFR_NEO4J_HTTP_PORT:-7474}"
export GOFR_NEO4J_BOLT_PORT="${GOFR_NEO4J_BOLT_PORT:-7687}"

# Reserved ports for future services:
# 8090-8092: Reserved
# 8100-8102: Reserved  
# 8110-8112: Reserved
# etc.

# Helper function to display all port assignments
gofr_ports_list() {
    echo "GOFR Service Port Assignments"
    echo "=============================="
    echo ""
    echo "MCP Services:"
    echo "  gofr-doc:  MCP=${GOFR_DOC_MCP_PORT}  MCPO=${GOFR_DOC_MCPO_PORT}  Web=${GOFR_DOC_WEB_PORT}"
    echo "  gofr-plot: MCP=${GOFR_PLOT_MCP_PORT} MCPO=${GOFR_PLOT_MCPO_PORT} Web=${GOFR_PLOT_WEB_PORT}"
    echo "  gofr-np:   MCP=${GOFR_NP_MCP_PORT}   MCPO=${GOFR_NP_MCPO_PORT}   Web=${GOFR_NP_WEB_PORT}"
    echo "  gofr-dig:  MCP=${GOFR_DIG_MCP_PORT}  MCPO=${GOFR_DIG_MCPO_PORT}  Web=${GOFR_DIG_WEB_PORT}"
    echo "  gofr-iq:   MCP=${GOFR_IQ_MCP_PORT}   MCPO=${GOFR_IQ_MCPO_PORT}   Web=${GOFR_IQ_WEB_PORT}"
    echo ""
    echo "Infrastructure:"
    echo "  vault:     Port=${GOFR_VAULT_PORT}"
    echo "  chroma:    Port=${GOFR_CHROMA_PORT}"
    echo "  neo4j:     HTTP=${GOFR_NEO4J_HTTP_PORT} Bolt=${GOFR_NEO4J_BOLT_PORT}"
}
export -f gofr_ports_list

# Helper function to get ports for a specific service
gofr_get_ports() {
    local service="${1}"
    case "${service}" in
        gofr-doc|doc)
            echo "MCP=${GOFR_DOC_MCP_PORT} MCPO=${GOFR_DOC_MCPO_PORT} Web=${GOFR_DOC_WEB_PORT}"
            ;;
        gofr-plot|plot)
            echo "MCP=${GOFR_PLOT_MCP_PORT} MCPO=${GOFR_PLOT_MCPO_PORT} Web=${GOFR_PLOT_WEB_PORT}"
            ;;
        gofr-np|np)
            echo "MCP=${GOFR_NP_MCP_PORT} MCPO=${GOFR_NP_MCPO_PORT} Web=${GOFR_NP_WEB_PORT}"
            ;;
        gofr-dig|dig)
            echo "MCP=${GOFR_DIG_MCP_PORT} MCPO=${GOFR_DIG_MCPO_PORT} Web=${GOFR_DIG_WEB_PORT}"
            ;;
        gofr-iq|iq)
            echo "MCP=${GOFR_IQ_MCP_PORT} MCPO=${GOFR_IQ_MCPO_PORT} Web=${GOFR_IQ_WEB_PORT}"
            ;;
        vault)
            echo "Port=${GOFR_VAULT_PORT} Token=${GOFR_VAULT_DEV_TOKEN}"
            ;;
        chroma)
            echo "Port=${GOFR_CHROMA_PORT}"
            ;;
        neo4j)
            echo "HTTP=${GOFR_NEO4J_HTTP_PORT} Bolt=${GOFR_NEO4J_BOLT_PORT}"
            ;;
        *)
            echo "Error: Unknown service '${service}'" >&2
            echo "Available services: gofr-doc, gofr-plot, gofr-np, gofr-dig, gofr-iq, vault, chroma, neo4j" >&2
            return 1
            ;;
    esac
}

# Export helper functions
export -f gofr_ports_list
export -f gofr_get_ports
