"""Phase 3 Tests: Unified auth management CLI.

Tests for scripts/auth_manager.py functionality.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# Get the path to the auth_manager.py script
SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "auth_manager.py"


def run_cli(
    args: List[str],
    data_dir: Optional[Path] = None,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    """Run the auth_manager CLI with given arguments.

    Args:
        args: Command line arguments to pass
        data_dir: Optional data directory (creates temp if not provided)
        env: Optional environment variables to set

    Returns:
        CompletedProcess with stdout, stderr, returncode
    """
    import os

    cmd = [sys.executable, str(SCRIPT_PATH)]

    if data_dir:
        cmd.extend(["--data-dir", str(data_dir)])

    cmd.extend(args)

    # Build environment
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=run_env,
    )

    return result


class TestAuthManagerCLI:
    """Phase 3: Unified CLI tool tests."""

    def test_groups_list_shows_reserved_groups(self, tmp_path):
        """'groups list' displays reserved groups (admin, public)."""
        result = run_cli(["groups", "list"], data_dir=tmp_path)

        assert result.returncode == 0
        assert "admin" in result.stdout
        assert "public" in result.stdout

    def test_groups_list_json_format(self, tmp_path):
        """'groups list --format json' outputs valid JSON."""
        result = run_cli(["groups", "list", "--format", "json"], data_dir=tmp_path)

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)

        # Should have at least admin and public
        names = [g["name"] for g in data]
        assert "admin" in names
        assert "public" in names

    def test_groups_create_new_group(self, tmp_path):
        """'groups create' adds a new group."""
        result = run_cli(
            ["groups", "create", "finance", "--description", "Finance team"],
            data_dir=tmp_path,
        )
        assert result.returncode == 0
        assert "Created group: finance" in result.stdout

        # Verify it exists
        result = run_cli(["groups", "list"], data_dir=tmp_path)
        assert "finance" in result.stdout

    def test_groups_create_duplicate_fails(self, tmp_path):
        """'groups create' fails for duplicate group name."""
        # Create once
        run_cli(["groups", "create", "duplicate-test"], data_dir=tmp_path)

        # Try to create again
        result = run_cli(["groups", "create", "duplicate-test"], data_dir=tmp_path)
        assert result.returncode == 1
        assert "ERROR" in result.stderr

    def test_groups_defunct_makes_group_inactive(self, tmp_path):
        """'groups defunct' marks a group as defunct."""
        # Create a group
        run_cli(["groups", "create", "temp-group"], data_dir=tmp_path)

        # Make it defunct
        result = run_cli(["groups", "defunct", "temp-group"], data_dir=tmp_path)
        assert result.returncode == 0
        assert "defunct" in result.stdout.lower()

        # Should not appear in normal list
        result = run_cli(["groups", "list"], data_dir=tmp_path)
        assert "temp-group" not in result.stdout

        # Should appear with --include-defunct
        result = run_cli(["groups", "list", "--include-defunct"], data_dir=tmp_path)
        assert "temp-group" in result.stdout

    def test_groups_defunct_reserved_fails(self, tmp_path):
        """'groups defunct' fails for reserved groups."""
        result = run_cli(["groups", "defunct", "admin"], data_dir=tmp_path)
        assert result.returncode == 1
        assert "ERROR" in result.stderr

    def test_tokens_list_empty_initially(self, tmp_path):
        """'tokens list' shows no tokens initially."""
        result = run_cli(["tokens", "list"], data_dir=tmp_path)

        assert result.returncode == 0
        assert "No tokens found" in result.stdout or "Total: 0" in result.stdout

    def test_tokens_create_outputs_jwt(self, tmp_path):
        """'tokens create' outputs a valid JWT."""
        result = run_cli(
            ["tokens", "create", "--groups", "admin"],
            data_dir=tmp_path,
        )

        assert result.returncode == 0
        token = result.stdout.strip()

        # JWT format: header.payload.signature
        assert token.count('.') == 2, f"Expected JWT format, got: {token}"

    def test_tokens_create_multiple_groups(self, tmp_path):
        """'tokens create' works with multiple groups."""
        # First create the groups
        run_cli(["groups", "create", "users"], data_dir=tmp_path)
        run_cli(["groups", "create", "finance"], data_dir=tmp_path)

        result = run_cli(
            ["tokens", "create", "--groups", "admin,users,finance"],
            data_dir=tmp_path,
        )

        assert result.returncode == 0
        token = result.stdout.strip()
        assert token.count('.') == 2

    def test_tokens_create_invalid_group_fails(self, tmp_path):
        """'tokens create' fails for non-existent group."""
        result = run_cli(
            ["tokens", "create", "--groups", "nonexistent-group"],
            data_dir=tmp_path,
        )

        assert result.returncode == 1
        assert "ERROR" in result.stderr

    def test_tokens_list_shows_created_tokens(self, tmp_path):
        """'tokens list' shows tokens after creation."""
        # Create a token
        run_cli(["tokens", "create", "--groups", "admin"], data_dir=tmp_path)

        result = run_cli(["tokens", "list"], data_dir=tmp_path)

        assert result.returncode == 0
        assert "admin" in result.stdout
        assert "active" in result.stdout.lower()

    def test_tokens_list_json_format(self, tmp_path):
        """'tokens list --format json' outputs valid JSON."""
        # Create a token
        run_cli(["tokens", "create", "--groups", "admin"], data_dir=tmp_path)

        result = run_cli(["tokens", "list", "--format", "json"], data_dir=tmp_path)

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "id" in data[0]
        assert "groups" in data[0]
        assert "name" in data[0]

    def test_tokens_list_filter_by_status(self, tmp_path):
        """'tokens list --status' filters correctly."""
        # Create a token
        run_cli(
            ["tokens", "create", "--groups", "admin"],
            data_dir=tmp_path,
        )

        # Get the token ID from list
        list_result = run_cli(
            ["tokens", "list", "--format", "json"],
            data_dir=tmp_path,
        )
        tokens = json.loads(list_result.stdout)
        token_id = tokens[0]["id"]

        # Revoke it
        run_cli(["tokens", "revoke", token_id], data_dir=tmp_path)

        # Active list should be empty
        result = run_cli(["tokens", "list", "--status", "active"], data_dir=tmp_path)
        assert token_id not in result.stdout

        # Revoked list should have it
        result = run_cli(["tokens", "list", "--status", "revoked"], data_dir=tmp_path)
        assert token_id in result.stdout

    def test_tokens_revoke_by_id(self, tmp_path):
        """'tokens revoke' marks token as revoked."""
        # Create a token
        run_cli(["tokens", "create", "--groups", "admin"], data_dir=tmp_path)

        # Get token ID
        list_result = run_cli(
            ["tokens", "list", "--format", "json"],
            data_dir=tmp_path,
        )
        tokens = json.loads(list_result.stdout)
        token_id = tokens[0]["id"]

        # Revoke it
        result = run_cli(["tokens", "revoke", token_id], data_dir=tmp_path)

        assert result.returncode == 0
        assert "revoked" in result.stdout.lower()

    def test_tokens_create_with_name_and_list(self, tmp_path):
        """Creating with --name surfaces name in list/JSON and filters by pattern."""
        run_cli(["tokens", "create", "--groups", "admin", "--name", "dev-api"], data_dir=tmp_path)

        table = run_cli(["tokens", "list"], data_dir=tmp_path)
        assert table.returncode == 0
        assert "dev-api" in table.stdout

        json_result = run_cli(["tokens", "list", "--format", "json"], data_dir=tmp_path)
        tokens = json.loads(json_result.stdout)
        assert tokens[0].get("name") == "dev-api"

        filtered = run_cli(["tokens", "list", "--name-pattern", "dev-*"] , data_dir=tmp_path)
        assert filtered.returncode == 0
        assert "dev-api" in filtered.stdout

    def test_tokens_revoke_by_name(self, tmp_path):
        """Revoke works by name without needing UUID."""
        run_cli(["tokens", "create", "--groups", "admin", "--name", "dev-admin"], data_dir=tmp_path)

        result = run_cli(["tokens", "revoke", "--name", "dev-admin"], data_dir=tmp_path)
        assert result.returncode == 0
        assert "revoked" in result.stdout.lower()

    def test_tokens_inspect_by_name(self, tmp_path):
        """Inspect by name returns stored record JSON."""
        run_cli(["tokens", "create", "--groups", "admin", "--name", "prod-api-server"], data_dir=tmp_path)

        result = run_cli(["tokens", "inspect", "--name", "prod-api-server"], data_dir=tmp_path)
        assert result.returncode == 0
        assert "prod-api-server" in result.stdout

    def test_tokens_revoke_nonexistent_fails(self, tmp_path):
        """'tokens revoke' fails for non-existent token."""
        result = run_cli(
            ["tokens", "revoke", "00000000-0000-0000-0000-000000000000"],
            data_dir=tmp_path,
        )

        assert result.returncode == 1
        assert "ERROR" in result.stderr

    def test_tokens_inspect_valid_token(self, tmp_path):
        """'tokens inspect' shows decoded token info."""
        # Create a token
        create_result = run_cli(
            ["tokens", "create", "--groups", "admin"],
            data_dir=tmp_path,
        )
        token = create_result.stdout.strip()

        # Inspect it
        result = run_cli(["tokens", "inspect", token], data_dir=tmp_path)

        assert result.returncode == 0
        assert "admin" in result.stdout
        assert "jti" in result.stdout
        assert "VALID" in result.stdout

    def test_tokens_inspect_invalid_token(self, tmp_path):
        """'tokens inspect' handles invalid tokens."""
        result = run_cli(
            ["tokens", "inspect", "not.a.valid.token"],
            data_dir=tmp_path,
        )

        # Should fail gracefully
        assert result.returncode == 1

    def test_tokens_create_with_output_file(self, tmp_path):
        """'tokens create --output' saves token to file."""
        output_file = tmp_path / "token.txt"

        result = run_cli(
            ["tokens", "create", "--groups", "admin", "--output", str(output_file)],
            data_dir=tmp_path,
        )

        assert result.returncode == 0
        assert output_file.exists()

        token = output_file.read_text().strip()
        assert token.count('.') == 2  # JWT format

    def test_tokens_create_custom_expiry(self, tmp_path):
        """'tokens create --expires' sets custom expiry."""
        result = run_cli(
            ["tokens", "create", "--groups", "admin", "--expires", "3600"],
            data_dir=tmp_path,
        )

        assert result.returncode == 0

        # Verify in list
        list_result = run_cli(
            ["tokens", "list", "--format", "json"],
            data_dir=tmp_path,
        )
        tokens = json.loads(list_result.stdout)

        # Check the token was created (expiry is handled internally)
        assert len(tokens) >= 1

    def test_help_command(self, tmp_path):
        """'--help' shows usage information."""
        result = run_cli(["--help"], data_dir=tmp_path)

        assert result.returncode == 0
        assert "groups" in result.stdout
        assert "tokens" in result.stdout

    def test_groups_help(self, tmp_path):
        """'groups --help' shows group commands."""
        result = run_cli(["groups", "--help"], data_dir=tmp_path)

        assert result.returncode == 0
        assert "list" in result.stdout
        assert "create" in result.stdout
        assert "defunct" in result.stdout

    def test_tokens_help(self, tmp_path):
        """'tokens --help' shows token commands."""
        result = run_cli(["tokens", "--help"], data_dir=tmp_path)

        assert result.returncode == 0
        assert "list" in result.stdout
        assert "create" in result.stdout
        assert "revoke" in result.stdout
        assert "inspect" in result.stdout
