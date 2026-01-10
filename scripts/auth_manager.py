#!/usr/bin/env python3
"""Unified auth management CLI for GOFR projects.

This script provides a single entry point for all authentication management
operations including group and token management.

Usage:
    python auth_manager.py groups list
    python auth_manager.py groups create <name> [--description DESC]
    python auth_manager.py groups defunct <name>

    python auth_manager.py tokens list [--status active|revoked]
    python auth_manager.py tokens create --groups admin,users [--expires SECONDS]
    python auth_manager.py tokens revoke <token-id>
    python auth_manager.py tokens inspect <token-string>

Environment Variables:
    GOFR_AUTH_BACKEND      Storage backend: memory, file, vault (default: file)
    GOFR_AUTH_DATA_DIR     Directory for auth data (default: data/auth)
    GOFR_JWT_SECRET        JWT signing secret (auto-generated if not set)
    GOFR_VAULT_URL         Vault server URL (if using vault backend)
    GOFR_VAULT_TOKEN       Vault auth token (if using vault backend)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

# Try to import from installed package, fall back to local path
try:
    from gofr_common.auth import (
        AuthService,
        FileGroupStore,
        FileTokenStore,
        GroupRegistry,
        MemoryGroupStore,
        MemoryTokenStore,
        VaultClient,
        VaultConfig,
        VaultGroupStore,
        VaultTokenStore,
    )
except ImportError:
    # Add potential paths for development
    script_dir = Path(__file__).parent.parent
    src_path = script_dir / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))
    from gofr_common.auth import (
        AuthService,
        FileGroupStore,
        FileTokenStore,
        GroupRegistry,
        MemoryGroupStore,
        MemoryTokenStore,
        VaultClient,
        VaultConfig,
        VaultGroupStore,
        VaultTokenStore,
    )

import jwt


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        return f"{seconds // 3600}h"
    else:
        return f"{seconds // 86400}d"


def format_time_remaining(expires_at: Optional[datetime]) -> str:
    """Format time remaining until expiry."""
    if expires_at is None:
        return "never"

    now = datetime.utcnow()
    if expires_at < now:
        return "EXPIRED"

    delta = expires_at - now
    days = delta.days
    hours = delta.seconds // 3600

    if days > 0:
        return f"{days}d {hours}h"
    elif hours > 0:
        return f"{hours}h"
    else:
        minutes = delta.seconds // 60
        return f"{minutes}m"


def create_auth_service(data_dir: str, backend: str = "file", quiet: bool = True) -> AuthService:
    """Create AuthService with the appropriate backend.

    Args:
        data_dir: Directory for auth data files
        backend: Storage backend type (memory, file)
        quiet: If True, suppress logging output (for CLI use)
    """
    # Suppress logging if quiet mode - must be done BEFORE any imports/inits
    if quiet:
        import logging
        logging.disable(logging.CRITICAL)

    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    if backend == "memory":
        token_store = MemoryTokenStore()
        group_store = MemoryGroupStore()
    elif backend == "file":
        token_store = FileTokenStore(data_path / "tokens.json")
        group_store = FileGroupStore(data_path / "groups.json")
    elif backend == "vault":
        # Get Vault configuration from environment
        vault_url = os.environ.get("GOFR_VAULT_URL", "http://localhost:8200")
        vault_token = os.environ.get("GOFR_VAULT_TOKEN")
        vault_path_prefix = os.environ.get("GOFR_VAULT_PATH_PREFIX", "gofr/auth")

        if not vault_token:
            print("ERROR: GOFR_VAULT_TOKEN environment variable required for vault backend", file=sys.stderr)
            sys.exit(1)

        config = VaultConfig(url=vault_url, token=vault_token)
        client = VaultClient(config)

        if not client.health_check():
            print(f"ERROR: Cannot connect to Vault at {vault_url}", file=sys.stderr)
            sys.exit(1)

        token_store = VaultTokenStore(client, path_prefix=vault_path_prefix)
        group_store = VaultGroupStore(client, path_prefix=vault_path_prefix)
    else:
        print(f"ERROR: Unsupported backend: {backend}", file=sys.stderr)
        sys.exit(1)

    group_registry = GroupRegistry(store=group_store, auto_bootstrap=True)

    # Get or generate JWT secret
    secret_key = os.environ.get("GOFR_JWT_SECRET")
    if not secret_key:
        # For CLI operations, we need a consistent secret
        # Check if there's a secret file
        secret_file = data_path / ".jwt_secret"
        if secret_file.exists():
            secret_key = secret_file.read_text().strip()
        else:
            import secrets
            secret_key = secrets.token_hex(32)
            secret_file.write_text(secret_key)
            if not quiet:
                print(f"Generated new JWT secret (saved to {secret_file})", file=sys.stderr)

    return AuthService(
        token_store=token_store,
        group_registry=group_registry,
        secret_key=secret_key,
    )


# ============================================================================
# GROUP COMMANDS
# ============================================================================

def cmd_groups_list(auth: AuthService, include_defunct: bool = False, format: str = "table") -> int:
    """List all groups."""
    groups = auth.groups.list_groups(include_defunct=include_defunct)

    if format == "json":
        output = [g.to_dict() for g in groups]
        print(json.dumps(output, indent=2, default=str))
        return 0

    # Table format
    if not groups:
        print("No groups found")
        return 0

    print(f"\n{'Name':<25} {'Status':<12} {'Reserved':<10} {'Created':<20}")
    print("-" * 70)

    for group in sorted(groups, key=lambda g: g.name):
        status = "active" if group.is_active else "defunct"
        reserved = "yes" if group.is_reserved else "no"
        created = group.created_at.strftime("%Y-%m-%d %H:%M")
        print(f"{group.name:<25} {status:<12} {reserved:<10} {created:<20}")

    print(f"\nTotal: {len(groups)} groups")
    return 0


def cmd_groups_create(auth: AuthService, name: str, description: Optional[str] = None) -> int:
    """Create a new group."""
    try:
        group = auth.groups.create_group(name, description=description)
        print(f"Created group: {name}")
        print(f"  ID: {group.id}")
        if description:
            print(f"  Description: {description}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_groups_defunct(auth: AuthService, name: str) -> int:
    """Make a group defunct (soft delete)."""
    group = auth.groups.get_group_by_name(name)
    if group is None:
        print(f"ERROR: Group '{name}' not found", file=sys.stderr)
        return 1

    try:
        auth.groups.make_defunct(group.id)
        print(f"Group '{name}' is now defunct")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


# ============================================================================
# TOKEN COMMANDS
# ============================================================================

def cmd_tokens_list(auth: AuthService, status: Optional[Literal["active", "revoked"]] = None, format: str = "table") -> int:
    """List all tokens."""
    tokens = auth.list_tokens(status=status)

    if format == "json":
        output = [t.to_dict() for t in tokens]
        print(json.dumps(output, indent=2, default=str))
        return 0

    # Table format
    if not tokens:
        print("No tokens found")
        return 0

    print(f"\n{'ID':<38} {'Status':<10} {'Groups':<25} {'Expires':<15}")
    print("-" * 90)

    for token in sorted(tokens, key=lambda t: t.created_at, reverse=True):
        token_id = str(token.id)
        status_str = token.status
        if token.is_expired and token.status == "active":
            status_str = "expired"
        groups_str = ",".join(token.groups)
        if len(groups_str) > 23:
            groups_str = groups_str[:20] + "..."
        expires_str = format_time_remaining(token.expires_at)

        print(f"{token_id:<38} {status_str:<10} {groups_str:<25} {expires_str:<15}")

    print(f"\nTotal: {len(tokens)} tokens")
    return 0


def cmd_tokens_create(auth: AuthService, groups: str, expires: int = 2592000, output: Optional[str] = None) -> int:
    """Create a new token."""
    group_list = [g.strip() for g in groups.split(",") if g.strip()]

    if not group_list:
        print("ERROR: At least one group is required", file=sys.stderr)
        return 1

    try:
        token = auth.create_token(groups=group_list, expires_in_seconds=expires)

        if output:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(token)
            print(f"Token saved to: {output}")
        else:
            # Print just the token for easy piping
            print(token)

        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_tokens_revoke(auth: AuthService, token_id: str) -> int:
    """Revoke a token by its ID."""
    # First, find the token record to get its JWT
    token_record = auth.get_token_by_id(token_id)

    if token_record is None:
        print(f"ERROR: Token '{token_id}' not found", file=sys.stderr)
        return 1

    if token_record.status == "revoked":
        print(f"Token '{token_id}' is already revoked")
        return 0

    # Create a minimal JWT just to call revoke_token
    # We need to forge a token with the correct jti for revocation
    payload = {
        "jti": token_id,
        "groups": token_record.groups,
        "iat": int(token_record.created_at.timestamp()),
        "exp": int(token_record.expires_at.timestamp()) if token_record.expires_at else 0,
    }
    minimal_token = jwt.encode(payload, auth.secret_key, algorithm="HS256")

    if auth.revoke_token(minimal_token):
        print(f"Token '{token_id}' has been revoked")
        return 0
    else:
        print(f"ERROR: Failed to revoke token '{token_id}'", file=sys.stderr)
        return 1


def cmd_tokens_inspect(auth: AuthService, token_string: str) -> int:
    """Inspect a token string (decode without verification)."""
    try:
        # First try to decode without verification to show claims
        unverified = jwt.decode(
            token_string,
            options={"verify_signature": False},
        )

        print("=== Token Claims (unverified) ===")
        print(json.dumps(unverified, indent=2, default=str))

        # Now try to verify
        print("\n=== Verification ===")
        try:
            info = auth.verify_token(token_string, require_store=True)
            print("Status: VALID")
            print(f"Groups: {', '.join(info.groups)}")
            print(f"Issued: {info.issued_at.isoformat()}")
            print(f"Expires: {info.expires_at.isoformat() if info.expires_at else 'never'}")

            # Check token record
            token_id = unverified.get("jti")
            if token_id:
                record = auth.get_token_by_id(token_id)
                if record:
                    print("\n=== Token Record ===")
                    print(f"ID: {record.id}")
                    print(f"Status: {record.status}")
                    print(f"Created: {record.created_at.isoformat()}")
                    if record.fingerprint:
                        print(f"Fingerprint: {record.fingerprint[:20]}...")
        except Exception as e:
            print(f"Status: INVALID - {e}")
            return 1

        return 0
    except jwt.DecodeError as e:
        print(f"ERROR: Invalid token format - {e}", file=sys.stderr)
        return 1


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Unified auth management CLI for GOFR projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global options
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("GOFR_AUTH_DATA_DIR", "data/auth"),
        help="Directory for auth data (default: data/auth or GOFR_AUTH_DATA_DIR)",
    )
    parser.add_argument(
        "--backend",
        default=os.environ.get("GOFR_AUTH_BACKEND", "file"),
        choices=["memory", "file"],
        help="Storage backend (default: file or GOFR_AUTH_BACKEND)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command category")

    # -------------------------------------------------------------------------
    # GROUPS subcommand
    # -------------------------------------------------------------------------
    groups_parser = subparsers.add_parser("groups", help="Group management")
    groups_sub = groups_parser.add_subparsers(dest="subcommand", help="Group operation")

    # groups list
    groups_list = groups_sub.add_parser("list", help="List all groups")
    groups_list.add_argument(
        "--include-defunct",
        action="store_true",
        help="Include defunct groups in listing",
    )
    groups_list.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    # groups create
    groups_create = groups_sub.add_parser("create", help="Create a new group")
    groups_create.add_argument("name", help="Group name")
    groups_create.add_argument(
        "--description", "-d",
        help="Group description",
    )

    # groups defunct
    groups_defunct = groups_sub.add_parser("defunct", help="Make a group defunct")
    groups_defunct.add_argument("name", help="Group name to make defunct")

    # -------------------------------------------------------------------------
    # TOKENS subcommand
    # -------------------------------------------------------------------------
    tokens_parser = subparsers.add_parser("tokens", help="Token management")
    tokens_sub = tokens_parser.add_subparsers(dest="subcommand", help="Token operation")

    # tokens list
    tokens_list = tokens_sub.add_parser("list", help="List all tokens")
    tokens_list.add_argument(
        "--status",
        choices=["active", "revoked"],
        help="Filter by status",
    )
    tokens_list.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    # tokens create
    tokens_create = tokens_sub.add_parser("create", help="Create a new token")
    tokens_create.add_argument(
        "--groups", "-g",
        required=True,
        help="Comma-separated list of groups (e.g., admin,users)",
    )
    tokens_create.add_argument(
        "--expires", "-e",
        type=int,
        default=2592000,  # 30 days
        help="Token expiry in seconds (default: 2592000 = 30 days)",
    )
    tokens_create.add_argument(
        "--output", "-o",
        help="Save token to file instead of stdout",
    )

    # tokens revoke
    tokens_revoke = tokens_sub.add_parser("revoke", help="Revoke a token")
    tokens_revoke.add_argument("token_id", help="Token ID (UUID) to revoke")

    # tokens inspect
    tokens_inspect = tokens_sub.add_parser("inspect", help="Inspect a token string")
    tokens_inspect.add_argument("token", help="JWT token string to inspect")

    args = parser.parse_args()

    # Handle no command
    if not args.command:
        parser.print_help()
        return 1

    # Handle no subcommand
    if args.command in ("groups", "tokens") and not args.subcommand:
        if args.command == "groups":
            groups_parser.print_help()
        else:
            tokens_parser.print_help()
        return 1

    # Create auth service (quiet mode unless verbose)
    auth = create_auth_service(args.data_dir, args.backend, quiet=not args.verbose)

    # Dispatch to appropriate command
    if args.command == "groups":
        if args.subcommand == "list":
            return cmd_groups_list(auth, args.include_defunct, args.format)
        elif args.subcommand == "create":
            return cmd_groups_create(auth, args.name, args.description)
        elif args.subcommand == "defunct":
            return cmd_groups_defunct(auth, args.name)

    elif args.command == "tokens":
        if args.subcommand == "list":
            return cmd_tokens_list(auth, args.status, args.format)
        elif args.subcommand == "create":
            return cmd_tokens_create(auth, args.groups, args.expires, args.output)
        elif args.subcommand == "revoke":
            return cmd_tokens_revoke(auth, args.token_id)
        elif args.subcommand == "inspect":
            return cmd_tokens_inspect(auth, args.token)

    return 0


if __name__ == "__main__":
    sys.exit(main())
