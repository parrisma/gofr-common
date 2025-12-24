"""Tests for storage backend protocols and memory implementations."""

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from gofr_common.auth.backends import (
    FileGroupStore,
    FileTokenStore,
    GroupStore,
    MemoryGroupStore,
    MemoryTokenStore,
    StorageError,
    StorageUnavailableError,
    TokenStore,
    VaultAuthenticationError,
    VaultClient,
    VaultConfig,
    VaultConfigError,
    VaultConnectionError,
    VaultError,
    VaultNotFoundError,
    VaultPermissionError,
)
from gofr_common.auth.groups import Group
from gofr_common.auth.tokens import TokenRecord

# ============================================================================
# Test Protocol Definitions
# ============================================================================


class TestTokenStoreProtocol:
    """Tests for TokenStore protocol definition."""

    def test_memory_store_is_token_store(self):
        """MemoryTokenStore implements TokenStore protocol."""
        store = MemoryTokenStore()
        assert isinstance(store, TokenStore)

    def test_protocol_has_required_methods(self):
        """TokenStore protocol defines all required methods."""
        assert hasattr(TokenStore, "get")
        assert hasattr(TokenStore, "put")
        assert hasattr(TokenStore, "list_all")
        assert hasattr(TokenStore, "exists")
        assert hasattr(TokenStore, "reload")


class TestGroupStoreProtocol:
    """Tests for GroupStore protocol definition."""

    def test_memory_store_is_group_store(self):
        """MemoryGroupStore implements GroupStore protocol."""
        store = MemoryGroupStore()
        assert isinstance(store, GroupStore)

    def test_protocol_has_required_methods(self):
        """GroupStore protocol defines all required methods."""
        assert hasattr(GroupStore, "get")
        assert hasattr(GroupStore, "get_by_name")
        assert hasattr(GroupStore, "put")
        assert hasattr(GroupStore, "list_all")
        assert hasattr(GroupStore, "exists")
        assert hasattr(GroupStore, "reload")


class TestStorageExceptions:
    """Tests for storage exceptions."""

    def test_storage_error_is_exception(self):
        """StorageError inherits from Exception."""
        assert issubclass(StorageError, Exception)

    def test_storage_unavailable_is_storage_error(self):
        """StorageUnavailableError inherits from StorageError."""
        assert issubclass(StorageUnavailableError, StorageError)

    def test_can_raise_storage_error(self):
        """StorageError can be raised and caught."""
        with pytest.raises(StorageError):
            raise StorageError("test error")

    def test_can_raise_storage_unavailable(self):
        """StorageUnavailableError can be raised and caught."""
        with pytest.raises(StorageUnavailableError):
            raise StorageUnavailableError("backend offline")


# ============================================================================
# Test MemoryTokenStore
# ============================================================================


class TestMemoryTokenStore:
    """Tests for MemoryTokenStore implementation."""

    @pytest.fixture
    def store(self):
        """Create a fresh MemoryTokenStore."""
        return MemoryTokenStore()

    @pytest.fixture
    def sample_record(self):
        """Create a sample TokenRecord."""
        return TokenRecord.create(
            groups=["admin"],
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

    def test_init_empty(self, store):
        """Store initializes empty."""
        assert len(store) == 0
        assert store.list_all() == {}

    def test_put_and_get(self, store, sample_record):
        """Can store and retrieve a token."""
        token_id = str(sample_record.id)
        store.put(token_id, sample_record)

        retrieved = store.get(token_id)
        assert retrieved is not None
        assert retrieved.id == sample_record.id
        assert retrieved.groups == sample_record.groups

    def test_get_nonexistent(self, store):
        """Getting nonexistent token returns None."""
        result = store.get("nonexistent-uuid")
        assert result is None

    def test_exists_true(self, store, sample_record):
        """exists() returns True for stored token."""
        token_id = str(sample_record.id)
        store.put(token_id, sample_record)
        assert store.exists(token_id) is True

    def test_exists_false(self, store):
        """exists() returns False for nonexistent token."""
        assert store.exists("nonexistent-uuid") is False

    def test_list_all(self, store):
        """list_all() returns all stored tokens."""
        records = [
            TokenRecord.create(groups=["admin"]),
            TokenRecord.create(groups=["users"]),
            TokenRecord.create(groups=["editors"]),
        ]

        for record in records:
            store.put(str(record.id), record)

        all_tokens = store.list_all()
        assert len(all_tokens) == 3

        # Verify it's a copy
        all_tokens["new-key"] = records[0]
        assert len(store) == 3  # Original unchanged

    def test_put_updates_existing(self, store, sample_record):
        """put() updates existing token."""
        token_id = str(sample_record.id)
        store.put(token_id, sample_record)

        # Update status
        updated = TokenRecord(
            id=sample_record.id,
            groups=sample_record.groups,
            status="revoked",
            created_at=sample_record.created_at,
            expires_at=sample_record.expires_at,
            revoked_at=datetime.utcnow(),
        )
        store.put(token_id, updated)

        retrieved = store.get(token_id)
        assert retrieved.status == "revoked"
        assert len(store) == 1

    def test_clear(self, store, sample_record):
        """clear() removes all tokens."""
        store.put(str(sample_record.id), sample_record)
        assert len(store) == 1

        store.clear()
        assert len(store) == 0
        assert store.list_all() == {}

    def test_reload_is_noop(self, store, sample_record):
        """reload() doesn't affect memory store."""
        store.put(str(sample_record.id), sample_record)
        store.reload()
        assert len(store) == 1

    def test_len(self, store):
        """__len__ returns correct count."""
        assert len(store) == 0

        for i in range(5):
            record = TokenRecord.create(groups=["test"])
            store.put(str(record.id), record)

        assert len(store) == 5


# ============================================================================
# Test MemoryGroupStore
# ============================================================================


class TestMemoryGroupStore:
    """Tests for MemoryGroupStore implementation."""

    @pytest.fixture
    def store(self):
        """Create a fresh MemoryGroupStore."""
        return MemoryGroupStore()

    @pytest.fixture
    def sample_group(self):
        """Create a sample Group."""
        return Group(
            id=uuid4(),
            name="testers",
            description="Test group",
            is_active=True,
            created_at=datetime.utcnow(),
        )

    def test_init_empty(self, store):
        """Store initializes empty."""
        assert len(store) == 0
        assert store.list_all() == {}

    def test_put_and_get(self, store, sample_group):
        """Can store and retrieve a group by ID."""
        group_id = str(sample_group.id)
        store.put(group_id, sample_group)

        retrieved = store.get(group_id)
        assert retrieved is not None
        assert retrieved.id == sample_group.id
        assert retrieved.name == sample_group.name

    def test_get_by_name(self, store, sample_group):
        """Can retrieve a group by name."""
        store.put(str(sample_group.id), sample_group)

        retrieved = store.get_by_name("testers")
        assert retrieved is not None
        assert retrieved.id == sample_group.id

    def test_get_by_name_nonexistent(self, store):
        """get_by_name() returns None for nonexistent group."""
        result = store.get_by_name("nonexistent")
        assert result is None

    def test_get_nonexistent(self, store):
        """get() returns None for nonexistent group."""
        result = store.get("nonexistent-uuid")
        assert result is None

    def test_exists_true(self, store, sample_group):
        """exists() returns True for stored group."""
        group_id = str(sample_group.id)
        store.put(group_id, sample_group)
        assert store.exists(group_id) is True

    def test_exists_false(self, store):
        """exists() returns False for nonexistent group."""
        assert store.exists("nonexistent-uuid") is False

    def test_list_all(self, store):
        """list_all() returns all stored groups."""
        groups = [
            Group(id=uuid4(), name="group1", created_at=datetime.utcnow()),
            Group(id=uuid4(), name="group2", created_at=datetime.utcnow()),
            Group(id=uuid4(), name="group3", created_at=datetime.utcnow()),
        ]

        for group in groups:
            store.put(str(group.id), group)

        all_groups = store.list_all()
        assert len(all_groups) == 3

    def test_put_updates_existing(self, store, sample_group):
        """put() updates existing group."""
        group_id = str(sample_group.id)
        store.put(group_id, sample_group)

        # Update description
        updated = Group(
            id=sample_group.id,
            name=sample_group.name,
            description="Updated description",
            is_active=sample_group.is_active,
            created_at=sample_group.created_at,
        )
        store.put(group_id, updated)

        retrieved = store.get(group_id)
        assert retrieved.description == "Updated description"
        assert len(store) == 1

    def test_put_updates_name_index(self, store, sample_group):
        """put() updates name index when name changes."""
        group_id = str(sample_group.id)
        store.put(group_id, sample_group)

        # Change name
        renamed = Group(
            id=sample_group.id,
            name="renamed",
            description=sample_group.description,
            is_active=sample_group.is_active,
            created_at=sample_group.created_at,
        )
        store.put(group_id, renamed)

        # Old name should not find it
        assert store.get_by_name("testers") is None
        # New name should find it
        assert store.get_by_name("renamed") is not None

    def test_clear(self, store, sample_group):
        """clear() removes all groups."""
        store.put(str(sample_group.id), sample_group)
        assert len(store) == 1

        store.clear()
        assert len(store) == 0
        assert store.list_all() == {}
        assert store.get_by_name(sample_group.name) is None

    def test_reload_is_noop(self, store, sample_group):
        """reload() doesn't affect memory store."""
        store.put(str(sample_group.id), sample_group)
        store.reload()
        assert len(store) == 1

    def test_len(self, store):
        """__len__ returns correct count."""
        assert len(store) == 0

        for i in range(5):
            group = Group(id=uuid4(), name=f"group{i}", created_at=datetime.utcnow())
            store.put(str(group.id), group)

        assert len(store) == 5

    def test_multiple_groups_by_name(self, store):
        """Can look up multiple groups by different names."""
        public = Group(id=uuid4(), name="public", is_reserved=True, created_at=datetime.utcnow())
        admin = Group(id=uuid4(), name="admin", is_reserved=True, created_at=datetime.utcnow())
        users = Group(id=uuid4(), name="users", created_at=datetime.utcnow())

        store.put(str(public.id), public)
        store.put(str(admin.id), admin)
        store.put(str(users.id), users)

        assert store.get_by_name("public").is_reserved is True
        assert store.get_by_name("admin").is_reserved is True
        assert store.get_by_name("users").is_reserved is False


# ============================================================================
# Test FileTokenStore
# ============================================================================


class TestFileTokenStore:
    """Tests for FileTokenStore implementation."""

    @pytest.fixture
    def temp_path(self, tmp_path):
        """Create a temporary file path."""
        return tmp_path / "tokens.json"

    @pytest.fixture
    def store(self, temp_path):
        """Create a FileTokenStore with temp file."""
        return FileTokenStore(temp_path)

    @pytest.fixture
    def sample_record(self):
        """Create a sample TokenRecord."""
        return TokenRecord.create(
            groups=["admin"],
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

    def test_file_store_is_token_store(self, store):
        """FileTokenStore implements TokenStore protocol."""
        assert isinstance(store, TokenStore)

    def test_init_creates_empty_store(self, store, temp_path):
        """Store initializes empty when file doesn't exist."""
        assert len(store) == 0
        assert not temp_path.exists()  # File not created until first put

    def test_put_creates_file(self, store, temp_path, sample_record):
        """put() creates the file if it doesn't exist."""
        token_id = str(sample_record.id)
        store.put(token_id, sample_record)

        assert temp_path.exists()
        assert len(store) == 1

    def test_put_and_get(self, store, sample_record):
        """Can store and retrieve a token."""
        token_id = str(sample_record.id)
        store.put(token_id, sample_record)

        retrieved = store.get(token_id)
        assert retrieved is not None
        assert retrieved.id == sample_record.id

    def test_persistence(self, temp_path, sample_record):
        """Data persists across store instances."""
        # Store data
        store1 = FileTokenStore(temp_path)
        token_id = str(sample_record.id)
        store1.put(token_id, sample_record)

        # Create new instance and verify
        store2 = FileTokenStore(temp_path)
        retrieved = store2.get(token_id)
        assert retrieved is not None
        assert retrieved.id == sample_record.id

    def test_reload(self, temp_path, sample_record):
        """reload() picks up external changes."""
        store1 = FileTokenStore(temp_path)
        token_id = str(sample_record.id)
        store1.put(token_id, sample_record)

        # Create second instance and modify
        store2 = FileTokenStore(temp_path)
        record2 = TokenRecord.create(groups=["users"])
        store2.put(str(record2.id), record2)

        # Store1 doesn't see change yet
        assert len(store1) == 1

        # After reload, sees both
        store1.reload()
        assert len(store1) == 2

    def test_list_all(self, store):
        """list_all() returns all tokens."""
        records = [
            TokenRecord.create(groups=["admin"]),
            TokenRecord.create(groups=["users"]),
        ]
        for r in records:
            store.put(str(r.id), r)

        all_tokens = store.list_all()
        assert len(all_tokens) == 2

    def test_exists(self, store, sample_record):
        """exists() works correctly."""
        token_id = str(sample_record.id)
        assert store.exists(token_id) is False

        store.put(token_id, sample_record)
        assert store.exists(token_id) is True

    def test_nested_path(self, tmp_path, sample_record):
        """Store creates parent directories."""
        nested_path = tmp_path / "deep" / "nested" / "tokens.json"
        store = FileTokenStore(nested_path)

        store.put(str(sample_record.id), sample_record)
        assert nested_path.exists()


# ============================================================================
# Test FileGroupStore
# ============================================================================


class TestFileGroupStore:
    """Tests for FileGroupStore implementation."""

    @pytest.fixture
    def temp_path(self, tmp_path):
        """Create a temporary file path."""
        return tmp_path / "groups.json"

    @pytest.fixture
    def store(self, temp_path):
        """Create a FileGroupStore with temp file."""
        return FileGroupStore(temp_path)

    @pytest.fixture
    def sample_group(self):
        """Create a sample Group."""
        return Group(
            id=uuid4(),
            name="testers",
            description="Test group",
            is_active=True,
            created_at=datetime.utcnow(),
        )

    def test_file_store_is_group_store(self, store):
        """FileGroupStore implements GroupStore protocol."""
        assert isinstance(store, GroupStore)

    def test_init_creates_empty_store(self, store, temp_path):
        """Store initializes empty when file doesn't exist."""
        assert len(store) == 0
        assert not temp_path.exists()

    def test_put_creates_file(self, store, temp_path, sample_group):
        """put() creates the file if it doesn't exist."""
        group_id = str(sample_group.id)
        store.put(group_id, sample_group)

        assert temp_path.exists()
        assert len(store) == 1

    def test_put_and_get(self, store, sample_group):
        """Can store and retrieve a group by ID."""
        group_id = str(sample_group.id)
        store.put(group_id, sample_group)

        retrieved = store.get(group_id)
        assert retrieved is not None
        assert retrieved.id == sample_group.id

    def test_get_by_name(self, store, sample_group):
        """Can retrieve a group by name."""
        store.put(str(sample_group.id), sample_group)

        retrieved = store.get_by_name("testers")
        assert retrieved is not None
        assert retrieved.id == sample_group.id

    def test_persistence(self, temp_path, sample_group):
        """Data persists across store instances."""
        store1 = FileGroupStore(temp_path)
        group_id = str(sample_group.id)
        store1.put(group_id, sample_group)

        store2 = FileGroupStore(temp_path)
        retrieved = store2.get(group_id)
        assert retrieved is not None
        assert retrieved.name == sample_group.name

    def test_name_index_persistence(self, temp_path, sample_group):
        """Name index is rebuilt on load."""
        store1 = FileGroupStore(temp_path)
        store1.put(str(sample_group.id), sample_group)

        store2 = FileGroupStore(temp_path)
        retrieved = store2.get_by_name("testers")
        assert retrieved is not None

    def test_reload(self, temp_path, sample_group):
        """reload() picks up external changes."""
        store1 = FileGroupStore(temp_path)
        store1.put(str(sample_group.id), sample_group)

        store2 = FileGroupStore(temp_path)
        group2 = Group(id=uuid4(), name="other", created_at=datetime.utcnow())
        store2.put(str(group2.id), group2)

        assert len(store1) == 1
        store1.reload()
        assert len(store1) == 2
        assert store1.get_by_name("other") is not None

    def test_list_all(self, store):
        """list_all() returns all groups."""
        groups = [
            Group(id=uuid4(), name="g1", created_at=datetime.utcnow()),
            Group(id=uuid4(), name="g2", created_at=datetime.utcnow()),
        ]
        for g in groups:
            store.put(str(g.id), g)

        all_groups = store.list_all()
        assert len(all_groups) == 2

    def test_exists(self, store, sample_group):
        """exists() works correctly."""
        group_id = str(sample_group.id)
        assert store.exists(group_id) is False

        store.put(group_id, sample_group)
        assert store.exists(group_id) is True

    def test_nested_path(self, tmp_path, sample_group):
        """Store creates parent directories."""
        nested_path = tmp_path / "deep" / "nested" / "groups.json"
        store = FileGroupStore(nested_path)

        store.put(str(sample_group.id), sample_group)
        assert nested_path.exists()


# ============================================================================
# Test VaultConfig
# ============================================================================


class TestVaultConfigCreation:
    """Tests for VaultConfig dataclass creation."""

    def test_create_with_token(self):
        """Create config with token authentication."""
        config = VaultConfig(
            url="https://vault.example.com:8200",
            token="hvs.test-token",
        )
        assert config.url == "https://vault.example.com:8200"
        assert config.token == "hvs.test-token"
        assert config.auth_method == "token"

    def test_create_with_approle(self):
        """Create config with AppRole authentication."""
        config = VaultConfig(
            url="https://vault.example.com:8200",
            role_id="role-123",
            secret_id="secret-456",
        )
        assert config.role_id == "role-123"
        assert config.secret_id == "secret-456"
        assert config.auth_method == "approle"

    def test_default_values(self):
        """Config has sensible defaults."""
        config = VaultConfig(url="https://vault.example.com", token="test")
        assert config.mount_point == "secret"
        assert config.path_prefix == "gofr/auth"
        assert config.timeout == 30
        assert config.verify_ssl is True
        assert config.namespace is None

    def test_url_trailing_slash_stripped(self):
        """Trailing slash is stripped from URL."""
        config = VaultConfig(
            url="https://vault.example.com:8200/",
            token="test",
        )
        assert config.url == "https://vault.example.com:8200"

    def test_custom_mount_and_prefix(self):
        """Custom mount point and path prefix."""
        config = VaultConfig(
            url="https://vault.example.com",
            token="test",
            mount_point="kv",
            path_prefix="myapp/secrets",
        )
        assert config.mount_point == "kv"
        assert config.path_prefix == "myapp/secrets"
        assert config.tokens_path == "myapp/secrets/tokens"
        assert config.groups_path == "myapp/secrets/groups"


class TestVaultConfigValidation:
    """Tests for VaultConfig.validate() method."""

    def test_validate_valid_token_config(self):
        """Valid token config passes validation."""
        config = VaultConfig(
            url="https://vault.example.com",
            token="hvs.test",
        )
        config.validate()  # Should not raise

    def test_validate_valid_approle_config(self):
        """Valid AppRole config passes validation."""
        config = VaultConfig(
            url="https://vault.example.com",
            role_id="role-123",
            secret_id="secret-456",
        )
        config.validate()  # Should not raise

    def test_validate_missing_url(self):
        """Missing URL raises VaultConfigError."""
        config = VaultConfig(url="", token="test")
        with pytest.raises(VaultConfigError, match="URL is required"):
            config.validate()

    def test_validate_invalid_url_scheme(self):
        """Invalid URL scheme raises VaultConfigError."""
        config = VaultConfig(url="ftp://vault.example.com", token="test")
        with pytest.raises(VaultConfigError, match="must start with http"):
            config.validate()

    def test_validate_no_auth(self):
        """Missing authentication raises VaultConfigError."""
        config = VaultConfig(url="https://vault.example.com")
        with pytest.raises(VaultConfigError, match="Must provide either"):
            config.validate()

    def test_validate_both_auth_methods(self):
        """Both token and AppRole raises VaultConfigError."""
        config = VaultConfig(
            url="https://vault.example.com",
            token="test",
            role_id="role-123",
            secret_id="secret-456",
        )
        with pytest.raises(VaultConfigError, match="not both"):
            config.validate()

    def test_validate_partial_approle(self):
        """Partial AppRole config raises VaultConfigError."""
        config = VaultConfig(
            url="https://vault.example.com",
            role_id="role-123",
            # Missing secret_id
        )
        with pytest.raises(VaultConfigError, match="both 'role_id' and 'secret_id'"):
            config.validate()

    def test_validate_invalid_timeout(self):
        """Invalid timeout raises VaultConfigError."""
        config = VaultConfig(
            url="https://vault.example.com",
            token="test",
            timeout=0,
        )
        with pytest.raises(VaultConfigError, match="Timeout must be positive"):
            config.validate()


class TestVaultConfigFromEnv:
    """Tests for VaultConfig.from_env() class method."""

    def test_from_env_with_token(self):
        """Load config from environment with token auth."""
        env = {
            "TEST_VAULT_URL": "https://vault.test.com:8200",
            "TEST_VAULT_TOKEN": "hvs.env-token",
        }
        with patch.dict(os.environ, env, clear=True):
            config = VaultConfig.from_env("TEST")

        assert config.url == "https://vault.test.com:8200"
        assert config.token == "hvs.env-token"
        assert config.auth_method == "token"

    def test_from_env_with_approle(self):
        """Load config from environment with AppRole auth."""
        env = {
            "TEST_VAULT_URL": "https://vault.test.com",
            "TEST_VAULT_ROLE_ID": "env-role",
            "TEST_VAULT_SECRET_ID": "env-secret",
        }
        with patch.dict(os.environ, env, clear=True):
            config = VaultConfig.from_env("TEST")

        assert config.role_id == "env-role"
        assert config.secret_id == "env-secret"
        assert config.auth_method == "approle"

    def test_from_env_missing_url(self):
        """Missing URL env var raises VaultConfigError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(VaultConfigError, match="Missing required"):
                VaultConfig.from_env("TEST")

    def test_from_env_custom_mount_and_prefix(self):
        """Custom mount and prefix from environment."""
        env = {
            "TEST_VAULT_URL": "https://vault.test.com",
            "TEST_VAULT_TOKEN": "token",
            "TEST_VAULT_MOUNT": "kv-v2",
            "TEST_VAULT_PATH_PREFIX": "apps/myapp",
        }
        with patch.dict(os.environ, env, clear=True):
            config = VaultConfig.from_env("TEST")

        assert config.mount_point == "kv-v2"
        assert config.path_prefix == "apps/myapp"

    def test_from_env_timeout(self):
        """Parse timeout from environment."""
        env = {
            "TEST_VAULT_URL": "https://vault.test.com",
            "TEST_VAULT_TOKEN": "token",
            "TEST_VAULT_TIMEOUT": "60",
        }
        with patch.dict(os.environ, env, clear=True):
            config = VaultConfig.from_env("TEST")

        assert config.timeout == 60

    def test_from_env_invalid_timeout_uses_default(self):
        """Invalid timeout falls back to default."""
        env = {
            "TEST_VAULT_URL": "https://vault.test.com",
            "TEST_VAULT_TOKEN": "token",
            "TEST_VAULT_TIMEOUT": "not-a-number",
        }
        with patch.dict(os.environ, env, clear=True):
            config = VaultConfig.from_env("TEST")

        assert config.timeout == 30

    def test_from_env_verify_ssl_false(self):
        """Parse SSL verification from environment."""
        env = {
            "TEST_VAULT_URL": "https://vault.test.com",
            "TEST_VAULT_TOKEN": "token",
            "TEST_VAULT_VERIFY_SSL": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            config = VaultConfig.from_env("TEST")

        assert config.verify_ssl is False

    def test_from_env_namespace(self):
        """Parse namespace from environment."""
        env = {
            "TEST_VAULT_URL": "https://vault.test.com",
            "TEST_VAULT_TOKEN": "token",
            "TEST_VAULT_NAMESPACE": "my-namespace",
        }
        with patch.dict(os.environ, env, clear=True):
            config = VaultConfig.from_env("TEST")

        assert config.namespace == "my-namespace"

    def test_from_env_prefix_normalization(self):
        """Prefix is normalized (uppercase, underscore)."""
        env = {
            "GOFR_DIG_VAULT_URL": "https://vault.test.com",
            "GOFR_DIG_VAULT_TOKEN": "token",
        }
        with patch.dict(os.environ, env, clear=True):
            # Should work with hyphen
            config = VaultConfig.from_env("gofr-dig")

        assert config.url == "https://vault.test.com"


class TestVaultConfigPaths:
    """Tests for VaultConfig path properties."""

    def test_tokens_path(self):
        """tokens_path returns correct path."""
        config = VaultConfig(
            url="https://vault.example.com",
            token="test",
            path_prefix="myapp/auth",
        )
        assert config.tokens_path == "myapp/auth/tokens"

    def test_groups_path(self):
        """groups_path returns correct path."""
        config = VaultConfig(
            url="https://vault.example.com",
            token="test",
            path_prefix="myapp/auth",
        )
        assert config.groups_path == "myapp/auth/groups"

    def test_default_paths(self):
        """Default path prefix produces expected paths."""
        config = VaultConfig(
            url="https://vault.example.com",
            token="test",
        )
        assert config.tokens_path == "gofr/auth/tokens"
        assert config.groups_path == "gofr/auth/groups"


# ============================================================================
# Test VaultClient
# ============================================================================


class TestVaultClientExceptions:
    """Tests for Vault exception hierarchy."""

    def test_vault_error_is_exception(self):
        """VaultError is an Exception."""
        assert issubclass(VaultError, Exception)

    def test_vault_connection_error_is_vault_error(self):
        """VaultConnectionError inherits from VaultError."""
        assert issubclass(VaultConnectionError, VaultError)

    def test_vault_auth_error_is_vault_error(self):
        """VaultAuthenticationError inherits from VaultError."""
        assert issubclass(VaultAuthenticationError, VaultError)

    def test_vault_not_found_error_is_vault_error(self):
        """VaultNotFoundError inherits from VaultError."""
        assert issubclass(VaultNotFoundError, VaultError)

    def test_vault_permission_error_is_vault_error(self):
        """VaultPermissionError inherits from VaultError."""
        assert issubclass(VaultPermissionError, VaultError)

    def test_can_raise_vault_errors(self):
        """All Vault errors can be raised and caught."""
        for exc_class in [
            VaultError,
            VaultConnectionError,
            VaultAuthenticationError,
            VaultNotFoundError,
            VaultPermissionError,
        ]:
            with pytest.raises(exc_class):
                raise exc_class("test error")


class TestVaultClientCreation:
    """Tests for VaultClient initialization."""

    @pytest.fixture
    def mock_hvac(self):
        """Mock hvac.Client."""
        with patch("gofr_common.auth.backends.vault_client.hvac") as mock:
            mock_client = MagicMock()
            mock_client.is_authenticated.return_value = True
            mock.Client.return_value = mock_client
            yield mock

    def test_create_with_token_auth(self, mock_hvac):
        """Create client with token authentication."""
        config = VaultConfig(
            url="https://vault.example.com:8200",
            token="hvs.test-token",
        )
        VaultClient(config)

        mock_hvac.Client.assert_called_once_with(
            url="https://vault.example.com:8200",
            token="hvs.test-token",
            namespace=None,
            verify=True,
            timeout=30,
        )

    def test_create_with_approle_auth(self, mock_hvac):
        """Create client with AppRole authentication."""
        mock_client = mock_hvac.Client.return_value
        mock_client.auth.approle.login.return_value = {
            "auth": {"client_token": "hvs.new-token"}
        }

        config = VaultConfig(
            url="https://vault.example.com:8200",
            role_id="role-123",
            secret_id="secret-456",
        )
        VaultClient(config)

        # Should call approle login
        mock_client.auth.approle.login.assert_called_once_with(
            role_id="role-123",
            secret_id="secret-456",
        )

    def test_approle_auth_failure(self, mock_hvac):
        """AppRole authentication failure raises VaultAuthenticationError."""
        mock_client = mock_hvac.Client.return_value
        mock_client.auth.approle.login.side_effect = Exception("Auth failed")

        config = VaultConfig(
            url="https://vault.example.com:8200",
            role_id="role-123",
            secret_id="secret-456",
        )

        with pytest.raises(VaultAuthenticationError, match="Auth failed"):
            VaultClient(config)

    def test_is_authenticated(self, mock_hvac):
        """is_authenticated() returns client auth status."""
        mock_client = mock_hvac.Client.return_value
        mock_client.is_authenticated.return_value = True

        config = VaultConfig(url="https://vault.example.com", token="test")
        client = VaultClient(config)

        assert client.is_authenticated() is True

        mock_client.is_authenticated.return_value = False
        assert client.is_authenticated() is False


class TestVaultClientHealthCheck:
    """Tests for VaultClient health check and reconnect."""

    @pytest.fixture
    def mock_hvac(self):
        """Mock hvac.Client."""
        with patch("gofr_common.auth.backends.vault_client.hvac") as mock:
            mock_client = MagicMock()
            mock_client.is_authenticated.return_value = True
            mock.Client.return_value = mock_client
            yield mock

    def test_health_check_healthy(self, mock_hvac):
        """health_check() returns True for healthy Vault."""
        mock_client = mock_hvac.Client.return_value
        mock_client.sys.read_health_status.return_value = {"initialized": True}

        config = VaultConfig(url="https://vault.example.com", token="test")
        client = VaultClient(config)

        assert client.health_check() is True

    def test_health_check_unhealthy(self, mock_hvac):
        """health_check() returns False when Vault is unavailable."""
        mock_client = mock_hvac.Client.return_value
        mock_client.sys.read_health_status.side_effect = Exception("Connection refused")

        config = VaultConfig(url="https://vault.example.com", token="test")
        client = VaultClient(config)

        assert client.health_check() is False

    def test_reconnect(self, mock_hvac):
        """reconnect() re-creates client and re-authenticates."""
        config = VaultConfig(url="https://vault.example.com", token="test")
        client = VaultClient(config)

        # First call is during init
        assert mock_hvac.Client.call_count == 1

        client.reconnect()

        # Second call after reconnect
        assert mock_hvac.Client.call_count == 2


class TestVaultClientReadSecret:
    """Tests for VaultClient.read_secret()."""

    @pytest.fixture
    def mock_hvac(self):
        """Mock hvac.Client."""
        with patch("gofr_common.auth.backends.vault_client.hvac") as mock:
            mock_client = MagicMock()
            mock_client.is_authenticated.return_value = True
            mock.Client.return_value = mock_client
            yield mock

    @pytest.fixture
    def client(self, mock_hvac):
        """Create VaultClient with mocked hvac."""
        config = VaultConfig(url="https://vault.example.com", token="test")
        return VaultClient(config)

    def test_read_secret_success(self, mock_hvac, client):
        """read_secret() returns secret data."""
        mock_client = mock_hvac.Client.return_value
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"key": "value", "foo": "bar"}}
        }

        result = client.read_secret("myapp/config")

        assert result == {"key": "value", "foo": "bar"}
        mock_client.secrets.kv.v2.read_secret_version.assert_called_once_with(
            path="myapp/config",
            mount_point="secret",
            raise_on_deleted_version=True,
        )

    def test_read_secret_not_found(self, mock_hvac, client):
        """read_secret() returns None for missing secrets."""
        mock_client = mock_hvac.Client.return_value
        # Import the actual exception to patch properly
        from gofr_common.auth.backends.vault_client import InvalidPath
        mock_client.secrets.kv.v2.read_secret_version.side_effect = InvalidPath()

        result = client.read_secret("nonexistent/path")

        assert result is None

    def test_read_secret_permission_denied(self, mock_hvac, client):
        """read_secret() raises VaultPermissionError on forbidden."""
        mock_client = mock_hvac.Client.return_value
        from gofr_common.auth.backends.vault_client import Forbidden
        mock_client.secrets.kv.v2.read_secret_version.side_effect = Forbidden()

        with pytest.raises(VaultPermissionError, match="Permission denied"):
            client.read_secret("secret/path")

    def test_read_secret_connection_error(self, mock_hvac, client):
        """read_secret() raises VaultConnectionError on failure."""
        mock_client = mock_hvac.Client.return_value
        mock_client.secrets.kv.v2.read_secret_version.side_effect = Exception("Network error")

        with pytest.raises(VaultConnectionError, match="Network error"):
            client.read_secret("secret/path")


class TestVaultClientWriteSecret:
    """Tests for VaultClient.write_secret()."""

    @pytest.fixture
    def mock_hvac(self):
        """Mock hvac.Client."""
        with patch("gofr_common.auth.backends.vault_client.hvac") as mock:
            mock_client = MagicMock()
            mock_client.is_authenticated.return_value = True
            mock.Client.return_value = mock_client
            yield mock

    @pytest.fixture
    def client(self, mock_hvac):
        """Create VaultClient with mocked hvac."""
        config = VaultConfig(url="https://vault.example.com", token="test")
        return VaultClient(config)

    def test_write_secret_success(self, mock_hvac, client):
        """write_secret() writes data to Vault."""
        mock_client = mock_hvac.Client.return_value

        client.write_secret("myapp/config", {"key": "value"})

        mock_client.secrets.kv.v2.create_or_update_secret.assert_called_once_with(
            path="myapp/config",
            secret={"key": "value"},
            mount_point="secret",
        )

    def test_write_secret_permission_denied(self, mock_hvac, client):
        """write_secret() raises VaultPermissionError on forbidden."""
        mock_client = mock_hvac.Client.return_value
        from gofr_common.auth.backends.vault_client import Forbidden
        mock_client.secrets.kv.v2.create_or_update_secret.side_effect = Forbidden()

        with pytest.raises(VaultPermissionError):
            client.write_secret("secret/path", {"key": "value"})

    def test_write_secret_connection_error(self, mock_hvac, client):
        """write_secret() raises VaultConnectionError on failure."""
        mock_client = mock_hvac.Client.return_value
        mock_client.secrets.kv.v2.create_or_update_secret.side_effect = Exception("Network")

        with pytest.raises(VaultConnectionError):
            client.write_secret("secret/path", {"key": "value"})


class TestVaultClientDeleteSecret:
    """Tests for VaultClient.delete_secret()."""

    @pytest.fixture
    def mock_hvac(self):
        """Mock hvac.Client."""
        with patch("gofr_common.auth.backends.vault_client.hvac") as mock:
            mock_client = MagicMock()
            mock_client.is_authenticated.return_value = True
            mock.Client.return_value = mock_client
            yield mock

    @pytest.fixture
    def client(self, mock_hvac):
        """Create VaultClient with mocked hvac."""
        config = VaultConfig(url="https://vault.example.com", token="test")
        return VaultClient(config)

    def test_delete_secret_success(self, mock_hvac, client):
        """delete_secret() returns True on success."""
        mock_client = mock_hvac.Client.return_value

        result = client.delete_secret("myapp/config")

        assert result is True
        mock_client.secrets.kv.v2.delete_latest_version_of_secret.assert_called_once()

    def test_delete_secret_not_found(self, mock_hvac, client):
        """delete_secret() returns False for missing secrets."""
        mock_client = mock_hvac.Client.return_value
        from gofr_common.auth.backends.vault_client import InvalidPath
        mock_client.secrets.kv.v2.delete_latest_version_of_secret.side_effect = InvalidPath()

        result = client.delete_secret("nonexistent/path")

        assert result is False


class TestVaultClientListSecrets:
    """Tests for VaultClient.list_secrets()."""

    @pytest.fixture
    def mock_hvac(self):
        """Mock hvac.Client."""
        with patch("gofr_common.auth.backends.vault_client.hvac") as mock:
            mock_client = MagicMock()
            mock_client.is_authenticated.return_value = True
            mock.Client.return_value = mock_client
            yield mock

    @pytest.fixture
    def client(self, mock_hvac):
        """Create VaultClient with mocked hvac."""
        config = VaultConfig(url="https://vault.example.com", token="test")
        return VaultClient(config)

    def test_list_secrets_success(self, mock_hvac, client):
        """list_secrets() returns list of keys."""
        mock_client = mock_hvac.Client.return_value
        mock_client.secrets.kv.v2.list_secrets.return_value = {
            "data": {"keys": ["key1", "key2", "key3"]}
        }

        result = client.list_secrets("myapp")

        assert result == ["key1", "key2", "key3"]

    def test_list_secrets_empty_path(self, mock_hvac, client):
        """list_secrets() returns empty list for nonexistent path."""
        mock_client = mock_hvac.Client.return_value
        from gofr_common.auth.backends.vault_client import InvalidPath
        mock_client.secrets.kv.v2.list_secrets.side_effect = InvalidPath()

        result = client.list_secrets("nonexistent")

        assert result == []


class TestVaultClientSecretExists:
    """Tests for VaultClient.secret_exists()."""

    @pytest.fixture
    def mock_hvac(self):
        """Mock hvac.Client."""
        with patch("gofr_common.auth.backends.vault_client.hvac") as mock:
            mock_client = MagicMock()
            mock_client.is_authenticated.return_value = True
            mock.Client.return_value = mock_client
            yield mock

    @pytest.fixture
    def client(self, mock_hvac):
        """Create VaultClient with mocked hvac."""
        config = VaultConfig(url="https://vault.example.com", token="test")
        return VaultClient(config)

    def test_secret_exists_true(self, mock_hvac, client):
        """secret_exists() returns True for existing secrets."""
        mock_client = mock_hvac.Client.return_value
        mock_client.secrets.kv.v2.read_secret_version.return_value = {"data": {}}

        assert client.secret_exists("myapp/config") is True

    def test_secret_exists_false(self, mock_hvac, client):
        """secret_exists() returns False for missing secrets."""
        mock_client = mock_hvac.Client.return_value
        from gofr_common.auth.backends.vault_client import InvalidPath
        mock_client.secrets.kv.v2.read_secret_version.side_effect = InvalidPath()

        assert client.secret_exists("nonexistent") is False


# ============================================================================
# Test VaultTokenStore
# ============================================================================


class TestVaultTokenStoreInit:
    """Tests for VaultTokenStore initialization."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        client = MagicMock(spec=VaultClient)
        client.read_secret.return_value = None
        client.write_secret.return_value = None
        client.delete_secret.return_value = True
        client.list_secrets.return_value = []
        client.secret_exists.return_value = False
        return client

    def test_init_with_defaults(self, mock_vault_client):
        """VaultTokenStore initializes with default path prefix."""
        from gofr_common.auth.backends import VaultTokenStore

        store = VaultTokenStore(mock_vault_client)

        assert store.client is mock_vault_client
        assert store.path_prefix == "gofr/auth"
        assert store._tokens_path == "gofr/auth/tokens"

    def test_init_with_custom_prefix(self, mock_vault_client):
        """VaultTokenStore accepts custom path prefix."""
        from gofr_common.auth.backends import VaultTokenStore

        store = VaultTokenStore(mock_vault_client, path_prefix="custom/path")

        assert store.path_prefix == "custom/path"
        assert store._tokens_path == "custom/path/tokens"

    def test_init_strips_trailing_slash(self, mock_vault_client):
        """Path prefix trailing slash is stripped."""
        from gofr_common.auth.backends import VaultTokenStore

        store = VaultTokenStore(mock_vault_client, path_prefix="custom/path/")

        assert store.path_prefix == "custom/path"
        assert store._tokens_path == "custom/path/tokens"


class TestVaultTokenStoreGet:
    """Tests for VaultTokenStore.get()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultTokenStore with mock client."""
        from gofr_common.auth.backends import VaultTokenStore
        return VaultTokenStore(mock_vault_client)

    @pytest.fixture
    def sample_record(self):
        """Create a sample TokenRecord."""
        return TokenRecord.create(groups=["admin"])

    def test_get_existing_token(self, store, mock_vault_client, sample_record):
        """get() returns TokenRecord for existing token."""
        mock_vault_client.read_secret.return_value = sample_record.to_dict()

        result = store.get(str(sample_record.id))

        assert result is not None
        assert result.id == sample_record.id
        assert result.groups == sample_record.groups
        mock_vault_client.read_secret.assert_called_once_with(
            f"gofr/auth/tokens/{sample_record.id}"
        )

    def test_get_nonexistent_token(self, store, mock_vault_client):
        """get() returns None for nonexistent token."""
        mock_vault_client.read_secret.return_value = None

        result = store.get("nonexistent-uuid")

        assert result is None

    def test_get_raises_on_connection_error(self, store, mock_vault_client):
        """get() raises StorageUnavailableError on connection failure."""
        mock_vault_client.read_secret.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.get("some-uuid")


class TestVaultTokenStorePut:
    """Tests for VaultTokenStore.put()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultTokenStore with mock client."""
        from gofr_common.auth.backends import VaultTokenStore
        return VaultTokenStore(mock_vault_client)

    @pytest.fixture
    def sample_record(self):
        """Create a sample TokenRecord."""
        return TokenRecord.create(groups=["admin"])

    def test_put_stores_token(self, store, mock_vault_client, sample_record):
        """put() writes token to Vault."""
        token_id = str(sample_record.id)

        store.put(token_id, sample_record)

        mock_vault_client.write_secret.assert_called_once()
        call_args = mock_vault_client.write_secret.call_args
        assert call_args[0][0] == f"gofr/auth/tokens/{token_id}"
        assert call_args[0][1]["id"] == token_id
        assert call_args[0][1]["groups"] == ["admin"]

    def test_put_raises_on_connection_error(self, store, mock_vault_client, sample_record):
        """put() raises StorageUnavailableError on connection failure."""
        mock_vault_client.write_secret.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.put(str(sample_record.id), sample_record)


class TestVaultTokenStoreDelete:
    """Tests for VaultTokenStore.delete()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultTokenStore with mock client."""
        from gofr_common.auth.backends import VaultTokenStore
        return VaultTokenStore(mock_vault_client)

    def test_delete_existing_token(self, store, mock_vault_client):
        """delete() returns True for existing token."""
        mock_vault_client.delete_secret.return_value = True

        result = store.delete("existing-uuid")

        assert result is True
        mock_vault_client.delete_secret.assert_called_once_with(
            "gofr/auth/tokens/existing-uuid"
        )

    def test_delete_nonexistent_token(self, store, mock_vault_client):
        """delete() returns False for nonexistent token."""
        mock_vault_client.delete_secret.return_value = False

        result = store.delete("nonexistent-uuid")

        assert result is False

    def test_delete_raises_on_connection_error(self, store, mock_vault_client):
        """delete() raises StorageUnavailableError on connection failure."""
        mock_vault_client.delete_secret.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.delete("some-uuid")


class TestVaultTokenStoreListAll:
    """Tests for VaultTokenStore.list_all()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultTokenStore with mock client."""
        from gofr_common.auth.backends import VaultTokenStore
        return VaultTokenStore(mock_vault_client)

    def test_list_all_empty(self, store, mock_vault_client):
        """list_all() returns empty dict when no tokens."""
        mock_vault_client.list_secrets.return_value = []

        result = store.list_all()

        assert result == {}

    def test_list_all_with_tokens(self, store, mock_vault_client):
        """list_all() returns all tokens."""
        token1 = TokenRecord.create(groups=["admin"])
        token2 = TokenRecord.create(groups=["users"])

        mock_vault_client.list_secrets.return_value = [str(token1.id), str(token2.id)]
        mock_vault_client.read_secret.side_effect = [
            token1.to_dict(),
            token2.to_dict(),
        ]

        result = store.list_all()

        assert len(result) == 2
        assert str(token1.id) in result
        assert str(token2.id) in result

    def test_list_all_skips_directories(self, store, mock_vault_client):
        """list_all() skips directory entries (trailing slash)."""
        token = TokenRecord.create(groups=["admin"])

        mock_vault_client.list_secrets.return_value = [str(token.id), "subdir/"]
        mock_vault_client.read_secret.return_value = token.to_dict()

        result = store.list_all()

        assert len(result) == 1
        assert str(token.id) in result

    def test_list_all_raises_on_connection_error(self, store, mock_vault_client):
        """list_all() raises StorageUnavailableError on connection failure."""
        mock_vault_client.list_secrets.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.list_all()


class TestVaultTokenStoreExists:
    """Tests for VaultTokenStore.exists()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultTokenStore with mock client."""
        from gofr_common.auth.backends import VaultTokenStore
        return VaultTokenStore(mock_vault_client)

    def test_exists_true(self, store, mock_vault_client):
        """exists() returns True for existing token."""
        mock_vault_client.secret_exists.return_value = True

        assert store.exists("existing-uuid") is True
        mock_vault_client.secret_exists.assert_called_once_with(
            "gofr/auth/tokens/existing-uuid"
        )

    def test_exists_false(self, store, mock_vault_client):
        """exists() returns False for nonexistent token."""
        mock_vault_client.secret_exists.return_value = False

        assert store.exists("nonexistent-uuid") is False

    def test_exists_raises_on_connection_error(self, store, mock_vault_client):
        """exists() raises StorageUnavailableError on connection failure."""
        mock_vault_client.secret_exists.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.exists("some-uuid")


class TestVaultTokenStoreReload:
    """Tests for VaultTokenStore.reload()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultTokenStore with mock client."""
        from gofr_common.auth.backends import VaultTokenStore
        return VaultTokenStore(mock_vault_client)

    def test_reload_is_noop(self, store, mock_vault_client):
        """reload() is a no-op for Vault backend."""
        store.reload()

        # Should not call any Vault methods
        mock_vault_client.read_secret.assert_not_called()
        mock_vault_client.list_secrets.assert_not_called()


class TestVaultTokenStoreClear:
    """Tests for VaultTokenStore.clear()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultTokenStore with mock client."""
        from gofr_common.auth.backends import VaultTokenStore
        return VaultTokenStore(mock_vault_client)

    def test_clear_deletes_all_tokens(self, store, mock_vault_client):
        """clear() deletes all tokens from Vault."""
        mock_vault_client.list_secrets.return_value = ["uuid1", "uuid2", "uuid3"]

        store.clear()

        assert mock_vault_client.delete_secret.call_count == 3

    def test_clear_skips_directories(self, store, mock_vault_client):
        """clear() skips directory entries."""
        mock_vault_client.list_secrets.return_value = ["uuid1", "subdir/"]

        store.clear()

        assert mock_vault_client.delete_secret.call_count == 1

    def test_clear_raises_on_connection_error(self, store, mock_vault_client):
        """clear() raises StorageUnavailableError on connection failure."""
        mock_vault_client.list_secrets.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.clear()


class TestVaultTokenStoreLen:
    """Tests for VaultTokenStore.__len__()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultTokenStore with mock client."""
        from gofr_common.auth.backends import VaultTokenStore
        return VaultTokenStore(mock_vault_client)

    def test_len_returns_token_count(self, store, mock_vault_client):
        """__len__() returns number of tokens."""
        mock_vault_client.list_secrets.return_value = ["uuid1", "uuid2", "uuid3"]

        assert len(store) == 3

    def test_len_excludes_directories(self, store, mock_vault_client):
        """__len__() excludes directory entries."""
        mock_vault_client.list_secrets.return_value = ["uuid1", "uuid2", "subdir/"]

        assert len(store) == 2

    def test_len_raises_on_connection_error(self, store, mock_vault_client):
        """__len__() raises StorageUnavailableError on connection failure."""
        mock_vault_client.list_secrets.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            len(store)


class TestVaultTokenStoreProtocolCompliance:
    """Tests that VaultTokenStore implements TokenStore protocol."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        client = MagicMock(spec=VaultClient)
        client.read_secret.return_value = None
        client.list_secrets.return_value = []
        client.secret_exists.return_value = False
        return client

    def test_implements_token_store(self, mock_vault_client):
        """VaultTokenStore implements TokenStore protocol."""
        from gofr_common.auth.backends import VaultTokenStore

        store = VaultTokenStore(mock_vault_client)

        assert isinstance(store, TokenStore)

    def test_has_all_protocol_methods(self, mock_vault_client):
        """VaultTokenStore has all required TokenStore methods."""
        from gofr_common.auth.backends import VaultTokenStore

        store = VaultTokenStore(mock_vault_client)

        assert hasattr(store, "get")
        assert hasattr(store, "put")
        assert hasattr(store, "list_all")
        assert hasattr(store, "exists")
        assert hasattr(store, "reload")


# ============================================================================
# Test VaultGroupStore
# ============================================================================


class TestVaultGroupStoreInit:
    """Tests for VaultGroupStore initialization."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        client = MagicMock(spec=VaultClient)
        client.read_secret.return_value = None
        client.write_secret.return_value = None
        client.delete_secret.return_value = True
        client.list_secrets.return_value = []
        client.secret_exists.return_value = False
        return client

    def test_init_with_defaults(self, mock_vault_client):
        """VaultGroupStore initializes with default path prefix."""
        from gofr_common.auth.backends import VaultGroupStore

        store = VaultGroupStore(mock_vault_client)

        assert store.client is mock_vault_client
        assert store.path_prefix == "gofr/auth"
        assert store._groups_path == "gofr/auth/groups"
        assert store._index_path == "gofr/auth/groups/_index/names"

    def test_init_with_custom_prefix(self, mock_vault_client):
        """VaultGroupStore accepts custom path prefix."""
        from gofr_common.auth.backends import VaultGroupStore

        store = VaultGroupStore(mock_vault_client, path_prefix="custom/path")

        assert store.path_prefix == "custom/path"
        assert store._groups_path == "custom/path/groups"

    def test_init_strips_trailing_slash(self, mock_vault_client):
        """Path prefix trailing slash is stripped."""
        from gofr_common.auth.backends import VaultGroupStore

        store = VaultGroupStore(mock_vault_client, path_prefix="custom/path/")

        assert store.path_prefix == "custom/path"
        assert store._groups_path == "custom/path/groups"


class TestVaultGroupStoreGet:
    """Tests for VaultGroupStore.get()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultGroupStore with mock client."""
        from gofr_common.auth.backends import VaultGroupStore
        return VaultGroupStore(mock_vault_client)

    @pytest.fixture
    def sample_group(self):
        """Create a sample Group."""
        return Group(id=uuid4(), name="test-group", description="Test group")

    def test_get_existing_group(self, store, mock_vault_client, sample_group):
        """get() returns Group for existing group."""
        mock_vault_client.read_secret.return_value = sample_group.to_dict()

        result = store.get(str(sample_group.id))

        assert result is not None
        assert result.id == sample_group.id
        assert result.name == sample_group.name
        mock_vault_client.read_secret.assert_called_once_with(
            f"gofr/auth/groups/{sample_group.id}"
        )

    def test_get_nonexistent_group(self, store, mock_vault_client):
        """get() returns None for nonexistent group."""
        mock_vault_client.read_secret.return_value = None

        result = store.get("nonexistent-uuid")

        assert result is None

    def test_get_raises_on_connection_error(self, store, mock_vault_client):
        """get() raises StorageUnavailableError on connection failure."""
        mock_vault_client.read_secret.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.get("some-uuid")


class TestVaultGroupStoreGetByName:
    """Tests for VaultGroupStore.get_by_name()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultGroupStore with mock client."""
        from gofr_common.auth.backends import VaultGroupStore
        return VaultGroupStore(mock_vault_client)

    @pytest.fixture
    def sample_group(self):
        """Create a sample Group."""
        return Group(id=uuid4(), name="admin", description="Admin group")

    def test_get_by_name_existing(self, store, mock_vault_client, sample_group):
        """get_by_name() returns Group for existing name."""
        group_id = str(sample_group.id)
        # First call returns index, second returns group
        mock_vault_client.read_secret.side_effect = [
            {"admin": group_id},  # Index lookup
            sample_group.to_dict(),  # Group data
        ]

        result = store.get_by_name("admin")

        assert result is not None
        assert result.name == "admin"
        assert mock_vault_client.read_secret.call_count == 2

    def test_get_by_name_not_in_index(self, store, mock_vault_client):
        """get_by_name() returns None when name not in index."""
        mock_vault_client.read_secret.return_value = {}  # Empty index

        result = store.get_by_name("nonexistent")

        assert result is None

    def test_get_by_name_empty_index(self, store, mock_vault_client):
        """get_by_name() returns None when index is empty."""
        mock_vault_client.read_secret.return_value = None

        result = store.get_by_name("admin")

        assert result is None


class TestVaultGroupStorePut:
    """Tests for VaultGroupStore.put()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultGroupStore with mock client."""
        from gofr_common.auth.backends import VaultGroupStore
        return VaultGroupStore(mock_vault_client)

    @pytest.fixture
    def sample_group(self):
        """Create a sample Group."""
        return Group(id=uuid4(), name="editors", description="Editor group")

    def test_put_stores_group(self, store, mock_vault_client, sample_group):
        """put() writes group to Vault and updates index."""
        group_id = str(sample_group.id)
        mock_vault_client.read_secret.side_effect = [
            None,  # No existing group
            {},    # Empty index
        ]

        store.put(group_id, sample_group)

        # Should write group data
        write_calls = mock_vault_client.write_secret.call_args_list
        assert len(write_calls) == 2

        # First call writes group
        assert write_calls[0][0][0] == f"gofr/auth/groups/{group_id}"
        assert write_calls[0][0][1]["name"] == "editors"

        # Second call updates index
        assert write_calls[1][0][0] == "gofr/auth/groups/_index/names"
        assert write_calls[1][0][1]["editors"] == group_id

    def test_put_updates_index_on_rename(self, store, mock_vault_client, sample_group):
        """put() removes old name from index on rename."""
        group_id = str(sample_group.id)
        old_group = Group(id=sample_group.id, name="old-name")
        old_group_dict = old_group.to_dict()

        mock_vault_client.read_secret.side_effect = [
            old_group_dict,  # Existing group with old name
            {"old-name": group_id},  # Index with old name
        ]

        store.put(group_id, sample_group)

        # Index should have new name, not old
        write_calls = mock_vault_client.write_secret.call_args_list
        index_call = write_calls[1][0][1]
        assert "old-name" not in index_call
        assert "editors" in index_call

    def test_put_raises_on_connection_error(self, store, mock_vault_client, sample_group):
        """put() raises StorageUnavailableError on connection failure."""
        mock_vault_client.read_secret.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.put(str(sample_group.id), sample_group)


class TestVaultGroupStoreDelete:
    """Tests for VaultGroupStore.delete()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultGroupStore with mock client."""
        from gofr_common.auth.backends import VaultGroupStore
        return VaultGroupStore(mock_vault_client)

    @pytest.fixture
    def sample_group(self):
        """Create a sample Group."""
        return Group(id=uuid4(), name="deleteme", description="Delete me")

    def test_delete_existing_group(self, store, mock_vault_client, sample_group):
        """delete() returns True and removes from index."""
        group_id = str(sample_group.id)
        mock_vault_client.read_secret.side_effect = [
            sample_group.to_dict(),  # Get group
            {"deleteme": group_id},  # Index
        ]
        mock_vault_client.delete_secret.return_value = True

        result = store.delete(group_id)

        assert result is True
        mock_vault_client.delete_secret.assert_called_once_with(
            f"gofr/auth/groups/{group_id}"
        )
        # Should update index
        assert mock_vault_client.write_secret.called

    def test_delete_nonexistent_group(self, store, mock_vault_client):
        """delete() returns False for nonexistent group."""
        mock_vault_client.read_secret.return_value = None
        mock_vault_client.delete_secret.return_value = False

        result = store.delete("nonexistent-uuid")

        assert result is False

    def test_delete_raises_on_connection_error(self, store, mock_vault_client):
        """delete() raises StorageUnavailableError on connection failure."""
        mock_vault_client.read_secret.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.delete("some-uuid")


class TestVaultGroupStoreListAll:
    """Tests for VaultGroupStore.list_all()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultGroupStore with mock client."""
        from gofr_common.auth.backends import VaultGroupStore
        return VaultGroupStore(mock_vault_client)

    def test_list_all_empty(self, store, mock_vault_client):
        """list_all() returns empty dict when no groups."""
        mock_vault_client.list_secrets.return_value = []

        result = store.list_all()

        assert result == {}

    def test_list_all_with_groups(self, store, mock_vault_client):
        """list_all() returns all groups."""
        group1 = Group(id=uuid4(), name="admin", description="Admin")
        group2 = Group(id=uuid4(), name="users", description="Users")

        mock_vault_client.list_secrets.return_value = [str(group1.id), str(group2.id)]
        mock_vault_client.read_secret.side_effect = [
            group1.to_dict(),
            group2.to_dict(),
        ]

        result = store.list_all()

        assert len(result) == 2
        assert str(group1.id) in result
        assert str(group2.id) in result

    def test_list_all_skips_index(self, store, mock_vault_client):
        """list_all() skips _index directory."""
        group = Group(id=uuid4(), name="admin")

        mock_vault_client.list_secrets.return_value = [str(group.id), "_index"]
        mock_vault_client.read_secret.return_value = group.to_dict()

        result = store.list_all()

        assert len(result) == 1
        # Should only read the group, not _index
        mock_vault_client.read_secret.assert_called_once()

    def test_list_all_skips_directories(self, store, mock_vault_client):
        """list_all() skips directory entries."""
        group = Group(id=uuid4(), name="admin")

        mock_vault_client.list_secrets.return_value = [str(group.id), "subdir/"]
        mock_vault_client.read_secret.return_value = group.to_dict()

        result = store.list_all()

        assert len(result) == 1

    def test_list_all_raises_on_connection_error(self, store, mock_vault_client):
        """list_all() raises StorageUnavailableError on connection failure."""
        mock_vault_client.list_secrets.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.list_all()


class TestVaultGroupStoreExists:
    """Tests for VaultGroupStore.exists()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultGroupStore with mock client."""
        from gofr_common.auth.backends import VaultGroupStore
        return VaultGroupStore(mock_vault_client)

    def test_exists_true(self, store, mock_vault_client):
        """exists() returns True for existing group."""
        mock_vault_client.secret_exists.return_value = True

        assert store.exists("existing-uuid") is True
        mock_vault_client.secret_exists.assert_called_once_with(
            "gofr/auth/groups/existing-uuid"
        )

    def test_exists_false(self, store, mock_vault_client):
        """exists() returns False for nonexistent group."""
        mock_vault_client.secret_exists.return_value = False

        assert store.exists("nonexistent-uuid") is False

    def test_exists_raises_on_connection_error(self, store, mock_vault_client):
        """exists() raises StorageUnavailableError on connection failure."""
        mock_vault_client.secret_exists.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.exists("some-uuid")


class TestVaultGroupStoreReload:
    """Tests for VaultGroupStore.reload()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultGroupStore with mock client."""
        from gofr_common.auth.backends import VaultGroupStore
        return VaultGroupStore(mock_vault_client)

    def test_reload_is_noop(self, store, mock_vault_client):
        """reload() is a no-op for Vault backend."""
        store.reload()

        mock_vault_client.read_secret.assert_not_called()
        mock_vault_client.list_secrets.assert_not_called()


class TestVaultGroupStoreClear:
    """Tests for VaultGroupStore.clear()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultGroupStore with mock client."""
        from gofr_common.auth.backends import VaultGroupStore
        return VaultGroupStore(mock_vault_client)

    def test_clear_deletes_all_groups(self, store, mock_vault_client):
        """clear() deletes all groups and index."""
        mock_vault_client.list_secrets.return_value = ["uuid1", "uuid2", "_index"]

        store.clear()

        # Should delete groups but not _index directly in loop
        delete_calls = mock_vault_client.delete_secret.call_args_list
        assert len(delete_calls) == 3  # 2 groups + index

    def test_clear_raises_on_connection_error(self, store, mock_vault_client):
        """clear() raises StorageUnavailableError on connection failure."""
        mock_vault_client.list_secrets.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            store.clear()


class TestVaultGroupStoreLen:
    """Tests for VaultGroupStore.__len__()."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        return MagicMock(spec=VaultClient)

    @pytest.fixture
    def store(self, mock_vault_client):
        """Create VaultGroupStore with mock client."""
        from gofr_common.auth.backends import VaultGroupStore
        return VaultGroupStore(mock_vault_client)

    def test_len_returns_group_count(self, store, mock_vault_client):
        """__len__() returns number of groups."""
        mock_vault_client.list_secrets.return_value = ["uuid1", "uuid2", "uuid3"]

        assert len(store) == 3

    def test_len_excludes_index(self, store, mock_vault_client):
        """__len__() excludes _index entry."""
        mock_vault_client.list_secrets.return_value = ["uuid1", "uuid2", "_index"]

        assert len(store) == 2

    def test_len_excludes_directories(self, store, mock_vault_client):
        """__len__() excludes directory entries."""
        mock_vault_client.list_secrets.return_value = ["uuid1", "uuid2", "subdir/"]

        assert len(store) == 2

    def test_len_raises_on_connection_error(self, store, mock_vault_client):
        """__len__() raises StorageUnavailableError on connection failure."""
        mock_vault_client.list_secrets.side_effect = VaultConnectionError("Network error")

        with pytest.raises(StorageUnavailableError, match="Vault unavailable"):
            len(store)


class TestVaultGroupStoreProtocolCompliance:
    """Tests that VaultGroupStore implements GroupStore protocol."""

    @pytest.fixture
    def mock_vault_client(self):
        """Create a mock VaultClient."""
        client = MagicMock(spec=VaultClient)
        client.read_secret.return_value = None
        client.list_secrets.return_value = []
        client.secret_exists.return_value = False
        return client

    def test_implements_group_store(self, mock_vault_client):
        """VaultGroupStore implements GroupStore protocol."""
        from gofr_common.auth.backends import VaultGroupStore

        store = VaultGroupStore(mock_vault_client)

        assert isinstance(store, GroupStore)

    def test_has_all_protocol_methods(self, mock_vault_client):
        """VaultGroupStore has all required GroupStore methods."""
        from gofr_common.auth.backends import VaultGroupStore

        store = VaultGroupStore(mock_vault_client)

        assert hasattr(store, "get")
        assert hasattr(store, "get_by_name")
        assert hasattr(store, "put")
        assert hasattr(store, "list_all")
        assert hasattr(store, "exists")
        assert hasattr(store, "reload")


# ============================================================================
# Test Store Factory
# ============================================================================


class TestCreateTokenStore:
    """Tests for create_token_store factory function."""

    def test_create_memory_store(self):
        """create_token_store creates MemoryTokenStore for 'memory' backend."""
        from gofr_common.auth.backends import MemoryTokenStore, create_token_store

        store = create_token_store("memory")

        assert isinstance(store, MemoryTokenStore)

    def test_create_file_store(self, tmp_path):
        """create_token_store creates FileTokenStore for 'file' backend."""
        from gofr_common.auth.backends import FileTokenStore, create_token_store

        store = create_token_store("file", path=tmp_path / "tokens.json")

        assert isinstance(store, FileTokenStore)

    def test_create_file_store_requires_path(self):
        """create_token_store raises FactoryError when path missing for file backend."""
        from gofr_common.auth.backends import FactoryError, create_token_store

        with pytest.raises(FactoryError, match="'path' is required"):
            create_token_store("file")

    def test_create_vault_store(self):
        """create_token_store creates VaultTokenStore for 'vault' backend."""
        from gofr_common.auth.backends import VaultTokenStore, create_token_store

        mock_client = MagicMock(spec=VaultClient)
        store = create_token_store("vault", vault_client=mock_client)

        assert isinstance(store, VaultTokenStore)

    def test_create_vault_store_requires_client(self):
        """create_token_store raises FactoryError when vault_client missing."""
        from gofr_common.auth.backends import FactoryError, create_token_store

        with pytest.raises(FactoryError, match="'vault_client' is required"):
            create_token_store("vault")

    def test_create_unknown_backend_raises(self):
        """create_token_store raises FactoryError for unknown backend."""
        from gofr_common.auth.backends import FactoryError, create_token_store

        with pytest.raises(FactoryError, match="Unknown backend type"):
            create_token_store("unknown")  # type: ignore

    def test_create_vault_store_with_custom_prefix(self):
        """create_token_store accepts custom vault_path_prefix."""
        from gofr_common.auth.backends import VaultTokenStore, create_token_store

        mock_client = MagicMock(spec=VaultClient)
        store = create_token_store(
            "vault",
            vault_client=mock_client,
            vault_path_prefix="custom/prefix",
        )

        assert isinstance(store, VaultTokenStore)
        assert store.path_prefix == "custom/prefix"


class TestCreateGroupStore:
    """Tests for create_group_store factory function."""

    def test_create_memory_store(self):
        """create_group_store creates MemoryGroupStore for 'memory' backend."""
        from gofr_common.auth.backends import MemoryGroupStore, create_group_store

        store = create_group_store("memory")

        assert isinstance(store, MemoryGroupStore)

    def test_create_file_store(self, tmp_path):
        """create_group_store creates FileGroupStore for 'file' backend."""
        from gofr_common.auth.backends import FileGroupStore, create_group_store

        store = create_group_store("file", path=tmp_path / "groups.json")

        assert isinstance(store, FileGroupStore)

    def test_create_file_store_requires_path(self):
        """create_group_store raises FactoryError when path missing for file backend."""
        from gofr_common.auth.backends import FactoryError, create_group_store

        with pytest.raises(FactoryError, match="'path' is required"):
            create_group_store("file")

    def test_create_vault_store(self):
        """create_group_store creates VaultGroupStore for 'vault' backend."""
        from gofr_common.auth.backends import VaultGroupStore, create_group_store

        mock_client = MagicMock(spec=VaultClient)
        store = create_group_store("vault", vault_client=mock_client)

        assert isinstance(store, VaultGroupStore)

    def test_create_vault_store_requires_client(self):
        """create_group_store raises FactoryError when vault_client missing."""
        from gofr_common.auth.backends import FactoryError, create_group_store

        with pytest.raises(FactoryError, match="'vault_client' is required"):
            create_group_store("vault")

    def test_create_unknown_backend_raises(self):
        """create_group_store raises FactoryError for unknown backend."""
        from gofr_common.auth.backends import FactoryError, create_group_store

        with pytest.raises(FactoryError, match="Unknown backend type"):
            create_group_store("unknown")  # type: ignore


class TestCreateStoresFromEnv:
    """Tests for create_stores_from_env factory function."""

    def test_default_to_memory(self, monkeypatch):
        """create_stores_from_env defaults to memory backend."""
        from gofr_common.auth.backends import (
            MemoryGroupStore,
            MemoryTokenStore,
            create_stores_from_env,
        )

        # Clear any backend env var
        monkeypatch.delenv("TEST_AUTH_BACKEND", raising=False)

        token_store, group_store = create_stores_from_env("TEST")

        assert isinstance(token_store, MemoryTokenStore)
        assert isinstance(group_store, MemoryGroupStore)

    def test_memory_backend(self, monkeypatch):
        """create_stores_from_env creates memory stores when specified."""
        from gofr_common.auth.backends import (
            MemoryGroupStore,
            MemoryTokenStore,
            create_stores_from_env,
        )

        monkeypatch.setenv("TEST_AUTH_BACKEND", "memory")

        token_store, group_store = create_stores_from_env("TEST")

        assert isinstance(token_store, MemoryTokenStore)
        assert isinstance(group_store, MemoryGroupStore)

    def test_file_backend(self, monkeypatch, tmp_path):
        """create_stores_from_env creates file stores when specified."""
        from gofr_common.auth.backends import (
            FileGroupStore,
            FileTokenStore,
            create_stores_from_env,
        )

        monkeypatch.setenv("TEST_AUTH_BACKEND", "file")
        monkeypatch.setenv("TEST_DATA_DIR", str(tmp_path))

        token_store, group_store = create_stores_from_env("TEST")

        assert isinstance(token_store, FileTokenStore)
        assert isinstance(group_store, FileGroupStore)
        assert token_store.path == tmp_path / "auth" / "tokens.json"
        assert group_store.path == tmp_path / "auth" / "groups.json"

    def test_file_backend_requires_data_dir(self, monkeypatch):
        """create_stores_from_env raises when DATA_DIR missing for file backend."""
        from gofr_common.auth.backends import FactoryError, create_stores_from_env

        monkeypatch.setenv("TEST_AUTH_BACKEND", "file")
        monkeypatch.delenv("TEST_DATA_DIR", raising=False)

        with pytest.raises(FactoryError, match="TEST_DATA_DIR is required"):
            create_stores_from_env("TEST")

    def test_vault_backend(self, monkeypatch):
        """create_stores_from_env creates vault stores when specified."""
        from gofr_common.auth.backends import (
            VaultGroupStore,
            VaultTokenStore,
            create_stores_from_env,
        )

        monkeypatch.setenv("TEST_AUTH_BACKEND", "vault")
        monkeypatch.setenv("TEST_VAULT_URL", "http://vault.test:8200")
        monkeypatch.setenv("TEST_VAULT_TOKEN", "test-token")

        with patch("gofr_common.auth.backends.vault_client.VaultClient") as mock_vc:
            mock_client = MagicMock()
            mock_vc.return_value = mock_client

            token_store, group_store = create_stores_from_env("TEST")

        assert isinstance(token_store, VaultTokenStore)
        assert isinstance(group_store, VaultGroupStore)

    def test_invalid_backend_raises(self, monkeypatch):
        """create_stores_from_env raises for invalid backend."""
        from gofr_common.auth.backends import FactoryError, create_stores_from_env

        monkeypatch.setenv("TEST_AUTH_BACKEND", "invalid")

        with pytest.raises(FactoryError, match="Invalid backend type 'invalid'"):
            create_stores_from_env("TEST")

    def test_prefix_with_trailing_underscore(self, monkeypatch):
        """create_stores_from_env handles prefix with trailing underscore."""
        from gofr_common.auth.backends import (
            MemoryTokenStore,
            create_stores_from_env,
        )

        monkeypatch.setenv("TEST_AUTH_BACKEND", "memory")

        # Should work with or without trailing underscore
        token_store, _ = create_stores_from_env("TEST_")

        assert isinstance(token_store, MemoryTokenStore)

    def test_backend_case_insensitive(self, monkeypatch):
        """create_stores_from_env handles backend case insensitively."""
        from gofr_common.auth.backends import (
            MemoryTokenStore,
            create_stores_from_env,
        )

        monkeypatch.setenv("TEST_AUTH_BACKEND", "MEMORY")

        token_store, _ = create_stores_from_env("TEST")

        assert isinstance(token_store, MemoryTokenStore)


class TestFactoryError:
    """Tests for FactoryError exception."""

    def test_factory_error_is_exception(self):
        """FactoryError inherits from Exception."""
        from gofr_common.auth.backends import FactoryError

        assert issubclass(FactoryError, Exception)

    def test_can_raise_factory_error(self):
        """FactoryError can be raised and caught."""
        from gofr_common.auth.backends import FactoryError

        with pytest.raises(FactoryError):
            raise FactoryError("test error")
