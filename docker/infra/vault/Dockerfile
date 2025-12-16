# =======================================================================
# HashiCorp Vault Docker Configuration for GOFR
# =======================================================================
# Dev mode: In-memory, auto-unsealed, KV v2 at 'secret/'
# =======================================================================

FROM hashicorp/vault:1.15

# Expose ports
# 8200 - API
# 8201 - Cluster (HA)
EXPOSE 8200 8201

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD vault status -address=http://127.0.0.1:8200 || exit 1

# Default: dev mode
# Root token is set via VAULT_DEV_ROOT_TOKEN_ID env var at runtime
CMD ["server", "-dev", "-dev-listen-address=0.0.0.0:8200"]
