"""Duplicate suppression cache for gossip messages."""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict

from chainbreaker.network.constants import (
    DEFAULT_GOSSIP_CACHE_MAX_ENTRIES,
    DEFAULT_GOSSIP_CACHE_TTL_SECONDS,
)


class GossipCache:
    """Bounded, time-expiring duplicate suppression cache."""

    def __init__(
        self,
        max_entries: int = DEFAULT_GOSSIP_CACHE_MAX_ENTRIES,
        ttl_seconds: float = DEFAULT_GOSSIP_CACHE_TTL_SECONDS,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        # Ordered by insertion; eviction uses FIFO + random sample in future.
        self._entries: OrderedDict[str, float] = OrderedDict()

    def _gossip_id(self, message_type: int, payload: bytes) -> str:
        raw = bytes([message_type]) + payload
        return hashlib.sha256(raw).hexdigest()

    def seen(self, message_type: int, payload: bytes) -> bool:
        """Check if a message has been seen; evicts expired entries first."""
        self._evict_expired()
        key = self._gossip_id(message_type, payload)
        if key in self._entries:
            self._entries.move_to_end(key)
            return True
        return False

    def add(self, message_type: int, payload: bytes) -> None:
        self._evict_expired()
        key = self._gossip_id(message_type, payload)
        if key in self._entries:
            self._entries.move_to_end(key)
            return
        while len(self._entries) >= self._max_entries:
            self._entries.popitem(last=False)
        self._entries[key] = time.monotonic()

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, t in self._entries.items() if now - t > self._ttl_seconds]
        for k in expired:
            del self._entries[k]

    @property
    def size(self) -> int:
        self._evict_expired()
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
