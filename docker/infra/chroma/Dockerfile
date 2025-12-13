# =======================================================================
# ChromaDB Docker Configuration for GOFR
# =======================================================================

FROM chromadb/chroma:0.5.23

# Environment
ENV IS_PERSISTENT=TRUE
ENV PERSIST_DIRECTORY=/chroma/chroma
ENV ANONYMIZED_TELEMETRY=FALSE

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/heartbeat || exit 1
