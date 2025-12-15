"""Group model and registry for multi-group authentication.

Provides a central registry of groups with support for:
- Reserved groups (public, admin) that cannot be made defunct
- File-based or in-memory storage
- Soft-delete (defunct) rather than hard delete
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional
from uuid import UUID, uuid4

from gofr_common.logger import Logger, create_logger


# Reserved group names that always exist and cannot be made defunct
RESERVED_GROUPS: FrozenSet[str] = frozenset({"public", "admin"})


@dataclass
class Group:
    """A group for access control.

    Attributes:
        id: Unique identifier for the group (UUID)
        name: Human-readable group name (unique)
        description: Optional description of the group's purpose
        is_active: Whether the group is currently active (not defunct)
        created_at: When the group was created
        defunct_at: When the group was made defunct (None if active)
        is_reserved: Whether this is a reserved system group
    """

    id: UUID
    name: str
    description: Optional[str] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    defunct_at: Optional[datetime] = None
    is_reserved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize group to dictionary for JSON storage."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "defunct_at": self.defunct_at.isoformat() if self.defunct_at else None,
            "is_reserved": self.is_reserved,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Group:
        """Deserialize group from dictionary.

        Args:
            data: Dictionary containing group data

        Returns:
            Group instance
        """
        return cls(
            id=UUID(data["id"]),
            name=data["name"],
            description=data.get("description"),
            is_active=data.get("is_active", True),
            created_at=datetime.fromisoformat(data["created_at"]),
            defunct_at=datetime.fromisoformat(data["defunct_at"]) if data.get("defunct_at") else None,
            is_reserved=data.get("is_reserved", False),
        )


class GroupRegistryError(Exception):
    """Base exception for group registry errors."""

    pass


class ReservedGroupError(GroupRegistryError):
    """Raised when attempting invalid operations on reserved groups."""

    pass


class DuplicateGroupError(GroupRegistryError):
    """Raised when attempting to create a group with a name that already exists."""

    pass


class GroupNotFoundError(GroupRegistryError):
    """Raised when a group is not found."""

    pass


class GroupRegistry:
    """Central registry for managing groups.

    Supports both file-based and in-memory storage. Reserved groups
    (public, admin) are automatically created and protected from
    being made defunct.

    Example:
        # File-based storage
        registry = GroupRegistry(store_path="/path/to/groups.json")

        # In-memory storage (for testing)
        registry = GroupRegistry(store_path=":memory:")

        # Create a group
        group = registry.create_group("users", "Regular users")

        # Get groups
        group = registry.get_group_by_name("admin")
        groups = registry.list_groups()

        # Make a group defunct (not allowed for reserved groups)
        registry.make_defunct(group.id)
    """

    def __init__(
        self,
        store_path: Optional[str] = None,
        logger: Optional[Logger] = None,
        auto_bootstrap: bool = True,
    ):
        """Initialize the group registry.

        Args:
            store_path: Path to groups.json file.
                       If ":memory:", uses in-memory storage.
                       If None, defaults to "data/auth/groups.json"
            logger: Optional logger instance
            auto_bootstrap: If True, automatically ensure reserved groups exist
        """
        if logger is not None:
            self.logger = logger
        else:
            self.logger = create_logger(name="group-registry")

        # Check for in-memory mode
        self._use_memory_store = store_path == ":memory:"

        if self._use_memory_store:
            self.store_path: Optional[Path] = None
            self._groups: Dict[str, Group] = {}  # keyed by UUID string
            self.logger.debug("GroupRegistry initialized with in-memory store")
        else:
            if store_path:
                self.store_path = Path(store_path)
            else:
                self.store_path = Path("data/auth/groups.json")
            self._groups = {}
            self._load_store()
            self.logger.debug(
                "GroupRegistry initialized",
                store_path=str(self.store_path),
                groups_count=len(self._groups),
            )

        # Bootstrap reserved groups if requested
        if auto_bootstrap:
            self.ensure_reserved_groups()

    def _load_store(self) -> None:
        """Load groups from disk."""
        if self._use_memory_store:
            return

        assert self.store_path is not None

        if self.store_path.exists():
            try:
                with open(self.store_path, "r") as f:
                    data = json.load(f)
                self._groups = {
                    group_id: Group.from_dict(group_data)
                    for group_id, group_data in data.items()
                }
                self.logger.debug(
                    "Group store loaded",
                    groups_count=len(self._groups),
                )
            except Exception as e:
                self.logger.error("Failed to load group store", error=str(e))
                self._groups = {}
        else:
            self._groups = {}

    def _save_store(self) -> None:
        """Save groups to disk."""
        if self._use_memory_store:
            return

        assert self.store_path is not None

        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.store_path, "w") as f:
                data = {
                    group_id: group.to_dict()
                    for group_id, group in self._groups.items()
                }
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            self.logger.debug("Group store saved", groups_count=len(self._groups))
        except Exception as e:
            self.logger.error("Failed to save group store", error=str(e))
            raise

    def ensure_reserved_groups(self) -> None:
        """Ensure reserved groups exist.

        Creates the public and admin groups if they don't already exist.
        This is called automatically on init with auto_bootstrap=True.
        """
        reserved_descriptions = {
            "public": "Universal access group - automatically included for all tokens",
            "admin": "Administrative access - required for group and token management",
        }

        created_any = False
        for name in RESERVED_GROUPS:
            existing = self.get_group_by_name(name)
            if existing is None:
                group = Group(
                    id=uuid4(),
                    name=name,
                    description=reserved_descriptions.get(name),
                    is_active=True,
                    created_at=datetime.utcnow(),
                    is_reserved=True,
                )
                self._groups[str(group.id)] = group
                created_any = True
                self.logger.info(f"Created reserved group: {name}", group_id=str(group.id))

        if created_any:
            self._save_store()

    def create_group(self, name: str, description: Optional[str] = None) -> Group:
        """Create a new group.

        Args:
            name: Name for the group (must be unique, cannot be reserved name)
            description: Optional description

        Returns:
            The created Group

        Raises:
            ReservedGroupError: If name is a reserved group name
            DuplicateGroupError: If a group with this name already exists
        """
        # Check for reserved names
        if name.lower() in RESERVED_GROUPS:
            raise ReservedGroupError(f"Cannot create group with reserved name: {name}")

        # Check for duplicates
        existing = self.get_group_by_name(name)
        if existing is not None:
            raise DuplicateGroupError(f"Group already exists: {name}")

        group = Group(
            id=uuid4(),
            name=name,
            description=description,
            is_active=True,
            created_at=datetime.utcnow(),
            is_reserved=False,
        )

        self._groups[str(group.id)] = group
        self._save_store()

        self.logger.info(
            "Group created",
            group_id=str(group.id),
            name=name,
        )

        return group

    def get_group(self, group_id: UUID) -> Optional[Group]:
        """Get a group by its UUID.

        Args:
            group_id: The UUID of the group

        Returns:
            The Group if found, None otherwise
        """
        return self._groups.get(str(group_id))

    def get_group_by_name(self, name: str) -> Optional[Group]:
        """Get a group by its name.

        Args:
            name: The name of the group

        Returns:
            The Group if found, None otherwise
        """
        for group in self._groups.values():
            if group.name == name:
                return group
        return None

    def list_groups(self, include_defunct: bool = False) -> List[Group]:
        """List all groups.

        Args:
            include_defunct: If True, include defunct groups

        Returns:
            List of groups
        """
        if include_defunct:
            return list(self._groups.values())
        return [g for g in self._groups.values() if g.is_active]

    def make_defunct(self, group_id: UUID) -> bool:
        """Mark a group as defunct (soft delete).

        Args:
            group_id: The UUID of the group to make defunct

        Returns:
            True if the group was made defunct

        Raises:
            GroupNotFoundError: If the group doesn't exist
            ReservedGroupError: If attempting to make a reserved group defunct
        """
        group = self.get_group(group_id)
        if group is None:
            raise GroupNotFoundError(f"Group not found: {group_id}")

        if group.is_reserved:
            raise ReservedGroupError(f"Cannot make reserved group defunct: {group.name}")

        if not group.is_active:
            self.logger.debug("Group already defunct", group_id=str(group_id))
            return False

        group.is_active = False
        group.defunct_at = datetime.utcnow()
        self._save_store()

        self.logger.info(
            "Group made defunct",
            group_id=str(group_id),
            name=group.name,
        )

        return True

    def get_reserved_group(self, name: str) -> Group:
        """Get a reserved group by name.

        Convenience method that asserts the group exists.

        Args:
            name: Reserved group name ('public' or 'admin')

        Returns:
            The Group

        Raises:
            ValueError: If name is not a reserved group name
            RuntimeError: If reserved group doesn't exist (shouldn't happen)
        """
        if name not in RESERVED_GROUPS:
            raise ValueError(f"Not a reserved group: {name}")

        group = self.get_group_by_name(name)
        if group is None:
            raise RuntimeError(f"Reserved group missing: {name}")

        return group
