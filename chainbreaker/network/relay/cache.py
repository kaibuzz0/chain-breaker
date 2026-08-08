"""Duplicate suppression cache for relayed blocks."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SeenEntry:
    """Record of a block the relay layer has already processed."""

    timestamp: float
    source_peer: str


class RelaySeenCache:
    """Bounded cache of block hashes already seen by relay."""

    def __init__(self, max_entries: int = 50_000, ttl_seconds: float = 7_200.0) -> None:
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._cache: OrderedDict[str, SeenEntry] = OrderedDict()

    def add(self, block_hash: str, source_peer: str, now: float | None = None) -> None:
        """Add a hash to the seen cache."""
        if now is None:
            now = time.monotonic()
        self._evict_expired(now)
        if block_hash in self._cache:
            return
        if len(self._cache) >= self._max_entries:
            self._cache.popitem(last=False)
        self._cache[block_hash] = SeenEntry(timestamp=now, source_peer=source_peer)

    def has(self, block_hash: str, now: float | None = None) -> bool:
        """Return True if the hash is in the cache and not expired."""
        if now is None:
            now = time.monotonic()
        entry = self._cache.get(block_hash)
        if entry is None:
            return False
        if now - entry.timestamp > self._ttl:
            self._cache.pop(block_hash, None)
            return False
        return True

    def size(self) -> int:
        return len(self._cache)

    def _evict_expired(self, now: float) -> None:
        expired = [h for h, e in self._cache.items() if now - e.timestamp > self._ttl]
        for h in expired:
            self._cache.pop(h, None)
