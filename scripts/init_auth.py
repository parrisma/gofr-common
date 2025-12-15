#!/usr/bin/env python3
"""Bootstrap script for initializing auth groups and creating initial admin token.

This script sets up the authentication system by:
1. Creating the groups.json file with reserved groups (public, admin)
2. Creating the tokens.json file with an initial admin token
3. Outputting the admin token for initial system access

Usage:
    python scripts/init_auth.py --data-dir /path/to/data/auth

    # Or with environment variable
    export GOFR_AUTH_DATA_DIR=/path/to/data/auth
    python scripts/init_auth.py

    # Output token to file instead of stdout
    python scripts/init_auth.py --data-dir /path/to/data/auth --output /path/to/admin-token.txt

    # Force recreate even if files exist
    python scripts/init_auth.py --data-dir /path/to/data/auth --force
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path for imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

from gofr_common.auth.groups import GroupRegistry, RESERVED_GROUPS


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Initialize auth system with reserved groups and admin token",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=os.environ.get("GOFR_AUTH_DATA_DIR", "data/auth"),
        help="Directory for auth data files (default: data/auth or GOFR_AUTH_DATA_DIR env)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="File to write admin token to (default: stdout)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recreation even if files already exist",
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


def main() -> int:
    """Main entry point."""
    args = parse_args()

    data_dir = Path(args.data_dir)
    groups_path = data_dir / "groups.json"
    tokens_path = data_dir / "tokens.json"

    # Check if already initialized
    if groups_path.exists() and tokens_path.exists() and not args.force:
        log(f"Auth files already exist in: {data_dir}", args.quiet)
        log("Use --force to reinitialize", args.quiet)

        # Still useful to show existing state
        registry = GroupRegistry(store_path=str(groups_path), auto_bootstrap=False)
        groups = registry.list_groups(include_defunct=True)
        log(f"Existing groups: {[g.name for g in groups]}", args.quiet)
        return 0

    # Create data directory
    data_dir.mkdir(parents=True, exist_ok=True)

    # Initialize AuthService (this creates reserved groups and token store)
    log(f"Initializing auth system at: {data_dir}", args.quiet)
    
    from gofr_common.auth import AuthService
    
    auth = AuthService(
        secret_key=args.secret,
        token_store_path=str(tokens_path),
        group_store_path=str(groups_path),
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
