#!/usr/bin/env python3
"""Bootstrap script for initializing auth groups and creating initial admin token.

This script sets up the authentication system by:
1. Creating reserved groups (public, admin) in the configured backend
2. Creating an initial admin token
3. Outputting the admin token for initial system access

Supports multiple backends:
- memory: In-memory storage (testing only, not persisted)
- file: JSON file storage (default, single-instance deployments)
- vault: HashiCorp Vault KV v2 (production, multi-instance deployments)

Usage:
    # File backend (default)
    python scripts/init_auth.py --data-dir /path/to/data/auth

    # Vault backend
    python scripts/init_auth.py --backend vault --vault-url http://vault:8200 --vault-token token

    # Or with environment variables
    export GOFR_AUTH_BACKEND=vault
    export GOFR_VAULT_URL=http://vault:8200
    export GOFR_VAULT_TOKEN=your-token
    python scripts/init_auth.py

    # Output token to file instead of stdout
    python scripts/init_auth.py --output /path/to/admin-token.txt

    # Force recreate even if already initialized
    python scripts/init_auth.py --force
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path for imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

from gofr_common.auth.groups import RESERVED_GROUPS


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Initialize auth system with reserved groups and admin token",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    # Backend selection
    parser.add_argument(
        "--backend",
        type=str,
        choices=["memory", "file", "vault"],
        default=os.environ.get("GOFR_AUTH_BACKEND", "file"),
        help="Storage backend (default: file or GOFR_AUTH_BACKEND env)",
    )
    
    # File backend options
    parser.add_argument(
        "--data-dir",
        type=str,
        default=os.environ.get("GOFR_AUTH_DATA_DIR", "data/auth"),
        help="Directory for auth data files - file backend only (default: data/auth)",
    )
    
    # Vault backend options
    parser.add_argument(
        "--vault-url",
        type=str,
        default=os.environ.get("GOFR_VAULT_URL", "http://localhost:8200"),
        help="Vault server URL (default: http://localhost:8200 or GOFR_VAULT_URL env)",
    )
    parser.add_argument(
        "--vault-token",
        type=str,
        default=os.environ.get("GOFR_VAULT_TOKEN"),
        help="Vault token for authentication (default: GOFR_VAULT_TOKEN env)",
    )
    parser.add_argument(
        "--vault-role-id",
        type=str,
        default=os.environ.get("GOFR_VAULT_ROLE_ID"),
        help="Vault AppRole role ID (default: GOFR_VAULT_ROLE_ID env)",
    )
    parser.add_argument(
        "--vault-secret-id",
        type=str,
        default=os.environ.get("GOFR_VAULT_SECRET_ID"),
        help="Vault AppRole secret ID (default: GOFR_VAULT_SECRET_ID env)",
    )
    parser.add_argument(
        "--vault-path-prefix",
        type=str,
        default=os.environ.get("GOFR_VAULT_PATH_PREFIX", "gofr/auth"),
        help="Path prefix in Vault (default: gofr/auth)",
    )
    
    # Common options
    parser.add_argument(
        "--output",
        type=str,
        help="File to write admin token to (default: stdout)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recreation even if already initialized",
    )
    parser.add_argument(
        "--secret",
        type=str,
        default=os.environ.get("GOFR_JWT_SECRET"),
        help="JWT secret for signing tokens (default: GOFR_JWT_SECRET env or auto-generate)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational output (only output token)",
    )
    return parser.parse_args()


def log(message: str, quiet: bool = False) -> None:
    """Print message unless quiet mode."""
    if not quiet:
        print(message, file=sys.stderr)


def create_stores(args: argparse.Namespace):
    """Create token and group stores based on backend selection."""
    from gofr_common.auth import (
        MemoryTokenStore,
        MemoryGroupStore,
        FileTokenStore,
        FileGroupStore,
        VaultConfig,
        VaultClient,
        VaultTokenStore,
        VaultGroupStore,
    )
    
    if args.backend == "memory":
        return MemoryTokenStore(), MemoryGroupStore()
    
    elif args.backend == "file":
        data_dir = Path(args.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        tokens_path = data_dir / "tokens.json"
        groups_path = data_dir / "groups.json"
        return FileTokenStore(path=str(tokens_path)), FileGroupStore(path=str(groups_path))
    
    elif args.backend == "vault":
        if not args.vault_token and not (args.vault_role_id and args.vault_secret_id):
            raise ValueError(
                "Vault backend requires --vault-token or both --vault-role-id and --vault-secret-id"
            )
        
        config = VaultConfig(
            url=args.vault_url,
            token=args.vault_token,
            role_id=args.vault_role_id,
            secret_id=args.vault_secret_id,
        )
        client = VaultClient(config)
        
        if not client.health_check():
            raise RuntimeError(f"Cannot connect to Vault at {args.vault_url}")
        
        return (
            VaultTokenStore(client, path_prefix=args.vault_path_prefix),
            VaultGroupStore(client, path_prefix=args.vault_path_prefix),
        )
    
    else:
        raise ValueError(f"Unknown backend: {args.backend}")


def check_existing(args: argparse.Namespace) -> bool:
    """Check if auth is already initialized. Returns True if exists."""
    if args.backend == "file":
        data_dir = Path(args.data_dir)
        groups_path = data_dir / "groups.json"
        tokens_path = data_dir / "tokens.json"
        return groups_path.exists() and tokens_path.exists()
    
    elif args.backend == "vault":
        # For Vault, check if reserved groups exist
        try:
            token_store, group_store = create_stores(args)
            # Check if admin group exists
            admin = group_store.get_by_name("admin")
            return admin is not None
        except Exception:
            return False
    
    return False


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Check if already initialized
    if check_existing(args) and not args.force:
        log(f"Auth system already initialized (backend: {args.backend})", args.quiet)
        log("Use --force to reinitialize", args.quiet)
        return 0

    # Create stores
    log(f"Initializing auth system (backend: {args.backend})", args.quiet)
    
    try:
        token_store, group_store = create_stores(args)
    except Exception as e:
        log(f"ERROR: Failed to create stores: {e}", args.quiet)
        return 1
    
    if args.backend == "file":
        log(f"  Data directory: {args.data_dir}", args.quiet)
    elif args.backend == "vault":
        log(f"  Vault URL: {args.vault_url}", args.quiet)
        log(f"  Path prefix: {args.vault_path_prefix}", args.quiet)

    # Initialize AuthService
    log("", args.quiet)
    
    from gofr_common.auth import AuthService, GroupRegistry
    
    groups = GroupRegistry(store=group_store)
    auth = AuthService(
        secret_key=args.secret,
        token_store=token_store,
        group_registry=groups,
    )

    # Verify reserved groups
    for name in RESERVED_GROUPS:
        group = auth.groups.get_group_by_name(name)
        if group is None:
            log(f"ERROR: Failed to create reserved group: {name}", args.quiet)
            return 1
        log(f"  Created group '{name}' (id: {group.id})", args.quiet)

    # Create initial admin token (never expires)
    log("", args.quiet)
    log("Creating admin token...", args.quiet)
    
    # Create a token that never expires (100 years)
    NEVER_EXPIRE = 100 * 365 * 24 * 60 * 60  # 100 years in seconds
    admin_token = auth.create_token(groups=["admin"], expires_in_seconds=NEVER_EXPIRE)
    
    log("", args.quiet)
    log("=" * 60, args.quiet)
    log("Auth system initialized successfully!", args.quiet)
    log("=" * 60, args.quiet)
    log("", args.quiet)
    log("Reserved groups created:", args.quiet)
    log("  - public: Universal access (auto-included in all token resolutions)", args.quiet)
    log("  - admin: Administrative access (required for group/token management)", args.quiet)
    log("", args.quiet)
    
    # Output token
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(admin_token)
        log(f"Admin token written to: {args.output}", args.quiet)
    else:
        log("Admin token (save this somewhere secure!):", args.quiet)
        log("", args.quiet)
        # Print token to stdout (not stderr, so it can be captured)
        print(admin_token)
    
    log("", args.quiet)
    log("IMPORTANT: Store this token securely. It grants full admin access.", args.quiet)

    return 0


if __name__ == "__main__":
    sys.exit(main())
