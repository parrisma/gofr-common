#!/usr/bin/env python3
"""Shared script to create groups across GOFR projects.

This script creates a JWT token for a new group, which is the fundamental
way to create groups in GOFR projects. Groups represent content sources and 
enforce strict access control.

This is a shared script that can be used by any GOFR project (gofr-iq, gofr-np, 
gofr-dig, etc.) by providing the appropriate environment variable prefix.

Usage:
    python create_group.py --prefix GOFR_IQ <group-name> [options]

Examples:
    # gofr-iq
    python create_group.py --prefix GOFR_IQ reuters-feed

    # gofr-np (news processing)
    python create_group.py --prefix GOFR_NP financial-news --expires 604800

    # gofr-dig (digital intelligence)
    python create_group.py --prefix GOFR_DIG research-team --output tokens/research.token

Environment Variables (per project):
    {PREFIX}_JWT_SECRET     JWT signing secret (required)
    {PREFIX}_TOKEN_STORE    Path to token store (optional)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Try to import from installed package, fall back to local path
try:
    from gofr_common.auth import AuthService
except ImportError:
    # Add potential paths for development
    script_dir = Path(__file__).parent.parent
    src_path = script_dir / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))
    from gofr_common.auth import AuthService


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


def list_groups(auth: AuthService, prefix: str) -> None:
    """List all existing groups from token store."""
    if not auth.token_store:
        print("No groups found (token store is empty)")
        return

    print("\n=== Existing Groups ===\n")
    
    groups_info = {}
    for token, metadata in auth.token_store.items():
        group = metadata.get("group")
        if not group:
            continue
        
        if group not in groups_info:
            groups_info[group] = {
                "tokens": 0,
                "latest_issued": None,
                "latest_expires": None,
            }
        
        groups_info[group]["tokens"] += 1
        
        issued = metadata.get("issued_at")
        expires = metadata.get("expires_at")
        
        if issued:
            if not groups_info[group]["latest_issued"] or issued > groups_info[group]["latest_issued"]:
                groups_info[group]["latest_issued"] = issued
        
        if expires:
            if not groups_info[group]["latest_expires"] or expires > groups_info[group]["latest_expires"]:
                groups_info[group]["latest_expires"] = expires
    
    if not groups_info:
        print("No groups found")
        return
    
    # Print in table format
    print(f"{'Group':<30} {'Tokens':<10} {'Latest Expires':<25}")
    print("-" * 65)
    
    for group in sorted(groups_info.keys()):
        info = groups_info[group]
        expires = info["latest_expires"]
        
        # Check if expired
        if expires:
            try:
                expires_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                now = datetime.utcnow().replace(tzinfo=expires_dt.tzinfo) if expires_dt.tzinfo else datetime.utcnow()
                
                if expires_dt < now:
                    expires_str = f"{expires} (EXPIRED)"
                else:
                    time_left = expires_dt - now
                    days_left = time_left.days
                    expires_str = f"{expires[:19]} ({days_left}d left)"
            except:
                expires_str = expires[:19] if expires else "N/A"
        else:
            expires_str = "N/A"
        
        print(f"{group:<30} {info['tokens']:<10} {expires_str:<25}")
    
    print(f"\nTotal groups: {len(groups_info)}")


def create_group(
    group_name: str,
    expires_in_seconds: int,
    output_file: str | None,
    auth: AuthService,
    prefix: str,
) -> None:
    """Create a new group by generating a JWT token."""
    
    # Validate group name
    if not group_name or not group_name.strip():
        print("ERROR: Group name cannot be empty", file=sys.stderr)
        sys.exit(1)
    
    # Check if group already exists
    existing_groups = set()
    for metadata in auth.token_store.values():
        if group := metadata.get("group"):
            existing_groups.add(group)
    
    if group_name in existing_groups:
        print(f"\nWARNING: Group '{group_name}' already exists with active tokens")
        response = input("Create another token for this group? [y/N]: ")
        if response.lower() != 'y':
            print("Aborted")
            sys.exit(0)
    
    # Create the token
    print(f"\nCreating group: {group_name}")
    print(f"Token expiry: {format_duration(expires_in_seconds)}")
    
    token = auth.create_token(
        group=group_name,
        expires_in_seconds=expires_in_seconds,
    )
    
    # Calculate expiry date
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
    
    print("\n=== Group Created Successfully ===\n")
    print(f"Group: {group_name}")
    print(f"Token: {token}")
    print(f"Expires: {expires_at.isoformat()}Z")
    print(f"Token Store: {auth.token_store_path}")
    
    # Save to file if requested
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w") as f:
            f.write(token)
        
        print(f"\nToken saved to: {output_path}")
    
    print("\n=== Usage Instructions ===\n")
    print("1. Use this token in Authorization header:")
    print(f"   Authorization: Bearer {token}\n")
    print("2. Create sources for this group using the MCP server")
    print("3. Ingest documents - they will automatically be assigned to this group")
    print("\nNote: Group name can be any string (e.g., 'reuters-feed', 'sales-team-nyc')")


def get_env_var(prefix: str, suffix: str) -> str | None:
    """Get environment variable with prefix."""
    var_name = f"{prefix}_{suffix}"
    return os.environ.get(var_name)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create a new group for GOFR projects by generating a JWT token",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # gofr-iq
  %(prog)s --prefix GOFR_IQ reuters-feed
  %(prog)s --prefix GOFR_IQ sales-team --expires 604800

  # gofr-np
  %(prog)s --prefix GOFR_NP financial-news
  
  # gofr-dig
  %(prog)s --prefix GOFR_DIG research-team --output tokens/research.token

  # List groups
  %(prog)s --prefix GOFR_IQ --list

Group Naming:
  - Use descriptive names (e.g., 'reuters-feed', 'sales-team-nyc')
  - Can be any string, not required to be UUID
  - 'public' is reserved for unauthenticated access

Environment Variables:
  {PREFIX}_JWT_SECRET      JWT signing secret (required)
  {PREFIX}_TOKEN_STORE     Path to token store (optional)
        """,
    )
    
    parser.add_argument(
        "--prefix",
        required=True,
        help="Environment variable prefix (e.g., 'GOFR_IQ', 'GOFR_NP', 'GOFR_DIG')",
    )
    
    parser.add_argument(
        "group_name",
        nargs="?",
        help="Name of the group to create (e.g., 'reuters-feed', 'sales-team')",
    )
    
    parser.add_argument(
        "--expires",
        type=int,
        default=2592000,  # 30 days
        help="Token expiry in seconds (default: 2592000 = 30 days)",
    )
    
    parser.add_argument(
        "--output",
        "-o",
        help="Save token to file (e.g., 'tokens/group.token')",
    )
    
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all existing groups",
    )
    
    parser.add_argument(
        "--token-store",
        help="Path to token store (overrides {PREFIX}_TOKEN_STORE env var)",
    )
    
    args = parser.parse_args()
    
    # Normalize prefix
    prefix = args.prefix.upper().replace("-", "_")
    
    # Get JWT secret
    secret_key = get_env_var(prefix, "JWT_SECRET")
    if not secret_key:
        print(f"ERROR: {prefix}_JWT_SECRET environment variable not set", file=sys.stderr)
        print("\nSet it in your environment or .env file:", file=sys.stderr)
        print(f"  export {prefix}_JWT_SECRET='your-secret-key'", file=sys.stderr)
        sys.exit(1)
    
    # Get token store path
    token_store = args.token_store or get_env_var(prefix, "TOKEN_STORE") or "data/auth/tokens.json"
    
    # Initialize auth service
    auth = AuthService(
        secret_key=secret_key,
        token_store_path=token_store,
        env_prefix=prefix,
    )
    
    # Handle list command
    if args.list:
        list_groups(auth, prefix)
        return
    
    # Validate group name is provided
    if not args.group_name:
        parser.print_help()
        print(f"\nERROR: group_name is required (or use --list to see existing groups)", file=sys.stderr)
        sys.exit(1)
    
    # Create the group
    create_group(
        group_name=args.group_name,
        expires_in_seconds=args.expires,
        output_file=args.output,
        auth=auth,
        prefix=prefix,
    )


if __name__ == "__main__":
    main()
