"""OpenRouter API key provider.

Reads the OpenRouter API key from Vault KV v2 with a TTL cache.

This is a core/shared secret (not project-specific). The default Vault path
matches the shared GOFR convention:

    gofr/config/api-keys/openrouter

The secret must contain a `value` key.
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Optional

from gofr_common.logger import Logger, create_logger

from .backends.vault_client import VaultClient


class OpenRouterKeyProvider:
    """Provides the OpenRouter API key with time-based cache refresh from Vault."""

    def __init__(
        self,
        vault_client: VaultClient,
        vault_path: str = "gofr/config/api-keys/openrouter",
        cache_ttl_seconds: int = 300,
        logger: Optional[Logger] = None,
    ) -> None:
        self._vault_client = vault_client
        self._vault_path = vault_path
        self._cache_ttl = cache_ttl_seconds
        self._logger = logger or create_logger(name="openrouter-key-provider")

        self._lock = threading.Lock()
        self._cached_key: Optional[str] = None
        self._cache_expires_at: float = 0.0

    def get(self) -> str:
        """Return the current OpenRouter API key, re-reading from Vault if cache expired."""
        with self._lock:
            now = time.monotonic()
            if self._cached_key is not None and now < self._cache_expires_at:
                return self._cached_key

            secret_data = self._vault_client.read_secret(self._vault_path)
            if not secret_data or "value" not in secret_data:
                raise RuntimeError(
                    f"OpenRouter API key not found at Vault path '{self._vault_path}' "
                    f"or missing 'value' key"
                )

            new_key: str = secret_data["value"]

            if self._cached_key is not None and new_key != self._cached_key:
                self._logger.warning(
                    "OpenRouter API key rotated in Vault",
                    old_fingerprint=self._fingerprint(self._cached_key),
                    new_fingerprint=self._fingerprint(new_key),
                    vault_path=self._vault_path,
                )

            self._cached_key = new_key
            self._cache_expires_at = now + self._cache_ttl

            self._logger.debug(
                "OpenRouter API key loaded from Vault",
                fingerprint=self._fingerprint(new_key),
                ttl_seconds=self._cache_ttl,
                vault_path=self._vault_path,
            )

            return self._cached_key

    @property
    def fingerprint(self) -> str:
        key = self.get()
        return self._fingerprint(key)

    def invalidate(self) -> None:
        with self._lock:
            self._cache_expires_at = 0.0

    @staticmethod
    def _fingerprint(value: str) -> str:
        digest = hashlib.sha256(value.encode()).hexdigest()
        return f"sha256:{digest[:12]}"
