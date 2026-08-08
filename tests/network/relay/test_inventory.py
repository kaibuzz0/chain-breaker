"""Tests for relay inventory tracker."""

from __future__ import annotations

import pytest

from chainbreaker.network.relay.inventory import InventoryEntry, InventoryTracker


def test_tracker_adds_pending() -> None:
    tracker = InventoryTracker(max_items=8)
    tracker.add_pending(InventoryEntry(inv_type="block", hash="a"))
    assert tracker.is_known("a") is True
    msg = tracker.build_inv_message()
    assert msg["hashes"] == ["a"]
    assert tracker.pending == []


def test_tracker_ignores_duplicate() -> None:
    tracker = InventoryTracker(max_items=8)
    tracker.add_pending(InventoryEntry(inv_type="block", hash="a"))
    tracker.add_pending(InventoryEntry(inv_type="block", hash="a"))
    assert len(tracker.pending) == 1


def test_tracker_enforces_limit() -> None:
    tracker = InventoryTracker(max_items=2)
    tracker.add_pending(InventoryEntry(inv_type="block", hash="a"))
    tracker.add_pending(InventoryEntry(inv_type="block", hash="b"))
    with pytest.raises(ValueError):
        tracker.add_pending(InventoryEntry(inv_type="block", hash="c"))
