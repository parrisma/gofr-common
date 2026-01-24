#!/usr/bin/env python3
"""
Shared Vault bootstrap: ensure JWT secret, reserved groups, and bootstrap tokens.
Uses existing gofr_common.auth bootstrap_auth logic against the shared Vault.
"""
import os
import sys
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SECRETS_DIR = PROJECT_ROOT / "secrets"

# Import bootstrap_auth from gofr-common
sys.path.insert(0, str(PROJECT_ROOT))
from scripts import bootstrap_auth  # type: ignore  # noqa: E402


def main() -> int:
    # Ensure secrets exist
    if not SECRETS_DIR.exists():
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        SECRETS_DIR.chmod(0o700)

    # Vault addr and token
    vault_addr = os.environ.get("VAULT_ADDR", "http://localhost:8201")
    root_token_file = SECRETS_DIR / "vault_root_token"
    root_token = os.environ.get("VAULT_TOKEN")
    if not root_token:
        if not root_token_file.exists():
            print("[ERROR] vault_root_token not found; run manage_vault.sh init", file=sys.stderr)
            return 1
        root_token = root_token_file.read_text().strip()

    # Set env for bootstrap_auth
    os.environ.setdefault("GOFR_AUTH_BACKEND", "vault")
    os.environ["GOFR_VAULT_URL"] = vault_addr
    os.environ["GOFR_VAULT_TOKEN"] = root_token
    os.environ.setdefault("GOFR_VAULT_PATH_PREFIX", "gofr/auth")
    os.environ.setdefault("GOFR_VAULT_MOUNT_POINT", "secret")

    # Run bootstrap_auth main
    return bootstrap_auth.main()


if __name__ == "__main__":
    sys.exit(main())
