# =======================================================================
# Neo4j Docker Configuration for GOFR
# =======================================================================

FROM neo4j:5.26-community

# Set environment variables
ENV NEO4J_AUTH=neo4j/gofr-neo4j-password
ENV NEO4J_PLUGINS=["apoc"]
ENV NEO4J_dbms_security_procedures_unrestricted=apoc.*
ENV NEO4J_dbms_security_procedures_allowlist=apoc.*

# Expose ports
# 7474: HTTP
# 7687: Bolt
EXPOSE 7474 7687

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -q --spider http://localhost:7474 || exit 1
