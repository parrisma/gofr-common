"""Tests for the shared runtime authorization decision cache."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gofr_common.auth import (
    AuthorizationDecisionCache,
    AuthorizationDecisionCacheKey,
    AuthorizationDecisionCacheMissError,
)


class TestAuthorizationDecisionCache:
    """Tests for fail-closed authorization decision caching."""

    def test_cache_returns_entry_before_expiry(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        cache = AuthorizationDecisionCache(ttl_seconds=30)
        key = AuthorizationDecisionCacheKey(token_id="token-1", group="plot.read")

        cache.put(key, allowed=True, now=now)
        entry = cache.require(key, now=now + timedelta(seconds=10))

        assert entry.allowed is True

    def test_cache_miss_is_fail_closed(self):
        cache = AuthorizationDecisionCache(ttl_seconds=30)
        key = AuthorizationDecisionCacheKey(token_id="token-1", group="plot.read")

        assert cache.get(key) is None
        with pytest.raises(AuthorizationDecisionCacheMissError, match="No valid cached"):
            cache.require(key)

    def test_cache_expiry_is_bounded_by_token_expiry(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        cache = AuthorizationDecisionCache(ttl_seconds=60)
        key = AuthorizationDecisionCacheKey(token_id="token-1", group="plot.read")
        token_expires_at = now + timedelta(seconds=15)

        entry = cache.put(key, allowed=False, token_expires_at=token_expires_at, now=now)

        assert entry.expires_at == token_expires_at
        assert cache.require(key, now=now + timedelta(seconds=14)).allowed is False
        with pytest.raises(AuthorizationDecisionCacheMissError):
            cache.require(key, now=now + timedelta(seconds=16))

    def test_cache_clear_removes_entries(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        cache = AuthorizationDecisionCache(ttl_seconds=30)
        key = AuthorizationDecisionCacheKey(token_id="token-1", resource="plot:chart-7")

        cache.put(key, allowed=True, now=now)
        cache.clear(key)

        assert cache.get(key, now=now + timedelta(seconds=1)) is None
