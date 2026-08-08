"""Inventory tracking for block announcements and requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    """A single block announcement entry."""

    inv_type: str
    hash: str


@dataclass
class InventoryTracker:
    """Track pending and announced inventory hashes."""

    max_items: int = 256
    pending: list[InventoryEntry] = field(default_factory=list)
    _known_hashes: set[str] = field(default_factory=set)

    def add_pending(self, entry: InventoryEntry) -> None:
        """Add an entry to the pending inventory if within limits."""
        if len(self.pending) >= self.max_items:
            raise ValueError("pending inventory full")
        if entry.hash in self._known_hashes:
            return
        self.pending.append(entry)
        self._known_hashes.add(entry.hash)

    def pop_pending(self) -> list[InventoryEntry]:
        """Return and clear pending inventory entries."""
        entries = list(self.pending)
        self.pending.clear()
        self._known_hashes.clear()
        return entries

    def mark_known(self, block_hash: str) -> None:
        """Record a hash as known without adding to pending."""
        self._known_hashes.add(block_hash)

    def is_known(self, block_hash: str) -> bool:
        return block_hash in self._known_hashes

    def build_inv_message(self) -> dict[str, Any]:
        """Serialize pending block entries to a payload dict."""
        entries = self.pop_pending()
        return {"type": "block", "hashes": [entry.hash for entry in entries]}
