"""Short-lived cache for yes-or-no runtime authorization decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from gofr_common.logger import Logger, create_logger


class AuthorizationDecisionCacheError(Exception):
    """Base error raised by the authorization decision cache."""


class AuthorizationDecisionCacheMissError(AuthorizationDecisionCacheError):
    """Raised when no still-valid cached authorization decision exists."""


@dataclass(frozen=True)
class AuthorizationDecisionCacheKey:
    """Cache key for a token and requested group or resource."""

    token_id: str
    group: str | None = None
    resource: str | None = None

    def __post_init__(self) -> None:
        token_id = self.token_id.strip()
        group = self.group.strip() if self.group and self.group.strip() else None
        resource = self.resource.strip() if self.resource and self.resource.strip() else None

        if not token_id:
            raise ValueError("token_id is required")
        if not group and not resource:
            raise ValueError("either group or resource must be provided")

        object.__setattr__(self, "token_id", token_id)
        object.__setattr__(self, "group", group)
        object.__setattr__(self, "resource", resource)


@dataclass(frozen=True)
class AuthorizationDecisionCacheEntry:
    """Cached authorization decision with expiry metadata."""

    key: AuthorizationDecisionCacheKey
    allowed: bool
    cached_at: datetime
    expires_at: datetime


class AuthorizationDecisionCache:
    """In-memory cache for short-lived runtime authorization decisions."""

    def __init__(
        self,
        ttl_seconds: int = 30,
        max_entries: int = 2048,
        logger: Logger | None = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._logger = logger or create_logger(name="authz-cache")
        self._entries: dict[AuthorizationDecisionCacheKey, AuthorizationDecisionCacheEntry] = {}

    def put(
        self,
        key: AuthorizationDecisionCacheKey,
        allowed: bool,
        *,
        token_expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> AuthorizationDecisionCacheEntry:
        current = now or self._now()
        expires_at = current + timedelta(seconds=self._ttl_seconds)
        if token_expires_at is not None and token_expires_at < expires_at:
            expires_at = token_expires_at

        entry = AuthorizationDecisionCacheEntry(
            key=key,
            allowed=allowed,
            cached_at=current,
            expires_at=expires_at,
        )

        if expires_at <= current:
            self._entries.pop(key, None)
            return entry

        self._entries[key] = entry
        self._prune(current)
        return entry

    def get(
        self,
        key: AuthorizationDecisionCacheKey,
        *,
        now: datetime | None = None,
    ) -> AuthorizationDecisionCacheEntry | None:
        current = now or self._now()
        entry = self._entries.get(key)
        if entry is None:
            return None
        if current >= entry.expires_at:
            self._entries.pop(key, None)
            return None
        return entry

    def require(
        self,
        key: AuthorizationDecisionCacheKey,
        *,
        now: datetime | None = None,
    ) -> AuthorizationDecisionCacheEntry:
        entry = self.get(key, now=now)
        if entry is None:
            raise AuthorizationDecisionCacheMissError(
                "No valid cached authorization decision exists"
            )
        return entry

    def clear(self, key: AuthorizationDecisionCacheKey | None = None) -> None:
        if key is None:
            self._entries.clear()
            return
        self._entries.pop(key, None)

    def __len__(self) -> int:
        return len(self._entries)

    def _prune(self, now: datetime) -> None:
        expired_keys = [key for key, entry in self._entries.items() if now >= entry.expires_at]
        for key in expired_keys:
            self._entries.pop(key, None)

        while len(self._entries) > self._max_entries:
            oldest_key = min(
                self._entries,
                key=lambda item_key: self._entries[item_key].expires_at,
            )
            self._entries.pop(oldest_key, None)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
