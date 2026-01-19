"""
Vault Access Policies
=====================
Defines HCL policies for service isolation (Least Privilege).

These policies are applied by VaultAdmin to restrict what each AppRole can access.
"""

# Base policy for all GOFR services - read shared config
POLICY_GLOBAL_READ = """
# Read global configuration (non-sensitive)
path "secret/data/global/config" {
  capabilities = ["read"]
}
"""

# Shared config policy - JWT signing secret etc
POLICY_GOFR_CONFIG_READ = """
# Read GOFR shared config (JWT signing, etc)
path "secret/data/gofr/config/*" {
  capabilities = ["read"]
}
# Read/write GOFR auth data (groups, tokens, etc) for authenticated services
path "secret/data/gofr/auth/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
# List auth paths
path "secret/metadata/gofr/auth/*" {
  capabilities = ["list", "read"]
}
"""

# MCP Service Policy
# - Read own secrets (OpenRouter keys, etc)
# - Read global config
# - Read GOFR shared config (JWT signing)
POLICY_MCP_READ = """
# Read MCP-specific secrets
path "secret/data/services/mcp/*" {
  capabilities = ["read"]
}
# Read specific token for this service if needed
path "secret/data/tokens/mcp" {
  capabilities = ["read"]
}
""" + POLICY_GLOBAL_READ + POLICY_GOFR_CONFIG_READ

# Web Service Policy
# - Read own secrets (Session keys, etc)
# - Read global config
# - Read GOFR shared config (JWT signing)
POLICY_WEB_READ = """
# Read Web-specific secrets
path "secret/data/services/web/*" {
  capabilities = ["read"]
}
# Read specific token for this service if needed
path "secret/data/tokens/web" {
  capabilities = ["read"]
}
""" + POLICY_GLOBAL_READ + POLICY_GOFR_CONFIG_READ

# Map of policy name -> HCL content
POLICIES = {
    "gofr-mcp-policy": POLICY_MCP_READ,
    "gofr-web-policy": POLICY_WEB_READ,
}
