"""In-memory storage backends for testing.

Provides simple dict-based storage that doesn't persist to disk.
Ideal for unit tests and development.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from ..tokens import TokenRecord

if TYPE_CHECKING:
    from ..groups import Group


class MemoryTokenStore:
    """In-memory token storage backend.

    Stores tokens in a simple dictionary. Data is lost when the
    instance is garbage collected. Thread-safe for single operations
    but not for compound operations.

    Example:
        store = MemoryTokenStore()
        store.put("uuid-1", token_record)
        record = store.get("uuid-1")
    """

    def __init__(self) -> None:
        """Initialize empty in-memory store."""
        self._store: Dict[str, TokenRecord] = {}

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
        """No-op for in-memory store."""
        pass

    def clear(self) -> None:
        """Clear all tokens from the store.

        Useful for test cleanup.
        """
        self._store.clear()

    def __len__(self) -> int:
        """Return number of tokens in store."""
        return len(self._store)


class MemoryGroupStore:
    """In-memory group storage backend.

    Stores groups in a simple dictionary with a name index for
    fast lookups by name. Data is lost when the instance is
    garbage collected.

    Example:
        store = MemoryGroupStore()
        store.put("uuid-1", group)
        group = store.get_by_name("admin")
    """

    def __init__(self) -> None:
        """Initialize empty in-memory store."""
        self._store: Dict[str, Group] = {}
        self._name_index: Dict[str, str] = {}  # name -> group_id

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
        # Remove old name index if updating
        old_group = self._store.get(group_id)
        if old_group and old_group.name != group.name:
            self._name_index.pop(old_group.name, None)

        self._store[group_id] = group
        self._name_index[group.name] = group_id

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
        """No-op for in-memory store."""
        pass

    def clear(self) -> None:
        """Clear all groups from the store.

        Useful for test cleanup.
        """
        self._store.clear()
        self._name_index.clear()

    def __len__(self) -> int:
        """Return number of groups in store."""
        return len(self._store)
