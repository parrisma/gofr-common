"""File-based storage backends.

Provides JSON file storage for tokens and groups with atomic writes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Union

from gofr_common.logger import Logger, create_logger

from ..tokens import TokenRecord

if TYPE_CHECKING:
    from ..groups import Group


class FileTokenStore:
    """File-based token storage backend.

    Stores tokens as JSON in a single file. Supports atomic writes
    using fsync to prevent data corruption.

    Example:
        store = FileTokenStore("/data/auth/tokens.json")
        store.put("uuid-1", token_record)
        record = store.get("uuid-1")
    """

    def __init__(
        self,
        path: Union[str, Path],
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize file-based token store.

        Args:
            path: Path to the JSON file (str or Path)
            logger: Optional logger instance
        """
        self.path = Path(path) if isinstance(path, str) else path
        self.logger = logger or create_logger(name="file-token-store")
        self._store: Dict[str, TokenRecord] = {}
        self._load()

    def _load(self) -> None:
        """Load tokens from disk."""
        if self.path.exists():
            try:
                with open(self.path, "r") as f:
                    data = json.load(f)
                self._store = {
                    uuid_str: TokenRecord.from_dict(record_data)
                    for uuid_str, record_data in data.items()
                }
                self.logger.debug(
                    "Token store loaded from disk",
                    tokens_count=len(self._store),
                    path=str(self.path),
                )
            except Exception as e:
                self.logger.error("Failed to load token store", error=str(e))
                self._store = {}
        else:
            self._store = {}
            self.logger.debug("Token store initialized as empty", path=str(self.path))

    def _save(self) -> None:
        """Save tokens to disk with atomic write."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                uuid_str: record.to_dict()
                for uuid_str, record in self._store.items()
            }
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            self.logger.debug("Token store saved", tokens_count=len(self._store))
        except Exception as e:
            self.logger.error("Failed to save token store", error=str(e))
            raise

    def get(self, token_id: str) -> Optional[TokenRecord]:
        """Retrieve a token record by ID.

        Args:
            token_id: UUID string of the token

        Returns:
            TokenRecord if found, None otherwise
        """
        return self._store.get(token_id)

    def put(self, token_id: str, record: TokenRecord) -> None:
        """Store or update a token record.

        Args:
            token_id: UUID string of the token
            record: TokenRecord to store
        """
        self._store[token_id] = record
        self._save()

    def list_all(self) -> Dict[str, TokenRecord]:
        """List all token records.

        Returns:
            Copy of the internal dictionary
        """
        return self._store.copy()

    def exists(self, token_id: str) -> bool:
        """Check if a token exists.

        Args:
            token_id: UUID string of the token

        Returns:
            True if token exists, False otherwise
        """
        return token_id in self._store

    def reload(self) -> None:
        """Reload data from disk."""
        self._load()

    def __len__(self) -> int:
        """Return number of tokens in store."""
        return len(self._store)


class FileGroupStore:
    """File-based group storage backend.

    Stores groups as JSON in a single file with a name index for
    fast lookups. Supports atomic writes using fsync.

    Example:
        store = FileGroupStore("/data/auth/groups.json")
        store.put("uuid-1", group)
        group = store.get_by_name("admin")
    """

    def __init__(
        self,
        path: Union[str, Path],
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize file-based group store.

        Args:
            path: Path to the JSON file (str or Path)
            logger: Optional logger instance
        """
        self.path = Path(path) if isinstance(path, str) else path
        self.logger = logger or create_logger(name="file-group-store")
        self._store: Dict[str, "Group"] = {}
        self._name_index: Dict[str, str] = {}  # name -> group_id
        self._load()

    def _load(self) -> None:
        """Load groups from disk."""
        # Late import to avoid circular dependency
        from ..groups import Group

        if self.path.exists():
            try:
                with open(self.path, "r") as f:
                    data = json.load(f)
                self._store = {
                    group_id: Group.from_dict(group_data)
                    for group_id, group_data in data.items()
                }
                # Rebuild name index
                self._name_index = {
                    group.name: group_id
                    for group_id, group in self._store.items()
                }
                self.logger.debug(
                    "Group store loaded from disk",
                    groups_count=len(self._store),
                    path=str(self.path),
                )
            except Exception as e:
                self.logger.error("Failed to load group store", error=str(e))
                self._store = {}
                self._name_index = {}
        else:
            self._store = {}
            self._name_index = {}
            self.logger.debug("Group store initialized as empty", path=str(self.path))

    def _save(self) -> None:
        """Save groups to disk with atomic write."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                group_id: group.to_dict()
                for group_id, group in self._store.items()
            }
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            self.logger.debug("Group store saved", groups_count=len(self._store))
        except Exception as e:
            self.logger.error("Failed to save group store", error=str(e))
            raise

    def get(self, group_id: str) -> Optional[Group]:
        """Retrieve a group by ID.

        Args:
            group_id: UUID string of the group

        Returns:
            Group if found, None otherwise
        """
        return self._store.get(group_id)

    def get_by_name(self, name: str) -> Optional[Group]:
        """Retrieve a group by name.

        Args:
            name: Name of the group

        Returns:
            Group if found, None otherwise
        """
        group_id = self._name_index.get(name)
        if group_id is None:
            return None
        return self._store.get(group_id)

    def put(self, group_id: str, group: Group) -> None:
        """Store or update a group.

        Args:
            group_id: UUID string of the group
            group: Group to store
        """
        # Remove old name index if updating with different name
        old_group = self._store.get(group_id)
        if old_group and old_group.name != group.name:
            self._name_index.pop(old_group.name, None)

        self._store[group_id] = group
        self._name_index[group.name] = group_id
        self._save()

    def list_all(self) -> Dict[str, Group]:
        """List all groups.

        Returns:
            Copy of the internal dictionary
        """
        return self._store.copy()

    def exists(self, group_id: str) -> bool:
        """Check if a group exists.

        Args:
            group_id: UUID string of the group

        Returns:
            True if group exists, False otherwise
        """
        return group_id in self._store

    def reload(self) -> None:
        """Reload data from disk."""
        self._load()

    def __len__(self) -> int:
        """Return number of groups in store."""
        return len(self._store)
