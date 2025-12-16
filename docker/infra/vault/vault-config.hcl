# =======================================================================
# HashiCorp Vault Server Configuration for GOFR
# =======================================================================
# This config is used for production mode (non-dev).
# Dev mode uses in-memory storage and auto-unseals.
# =======================================================================

# Storage backend - file-based for persistence
storage "file" {
  path = "/vault/data"
}

# Listener configuration
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true  # TLS handled by reverse proxy in production
}

# API address for client redirects
api_addr = "http://0.0.0.0:8200"

# Cluster address for HA (if needed later)
cluster_addr = "http://0.0.0.0:8201"

# Disable memory locking (required for containers without IPC_LOCK)
disable_mlock = true

# UI enabled for debugging (disable in hardened production)
ui = true

# Telemetry (optional)
telemetry {
  disable_hostname = true
}

# Log level
log_level = "info"
