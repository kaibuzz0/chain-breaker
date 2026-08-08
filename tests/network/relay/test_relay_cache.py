"""Tests for relay duplicate cache."""

from __future__ import annotations

from chainbreaker.network.relay.cache import RelaySeenCache


def test_cache_adds_and_checks() -> None:
    cache = RelaySeenCache(max_entries=10, ttl_seconds=60.0)
    cache.add("hash1", "peer-a", now=0.0)
    assert cache.has("hash1", now=1.0) is True
    assert cache.has("hash2", now=1.0) is False


def test_cache_evicts_on_full() -> None:
    cache = RelaySeenCache(max_entries=2, ttl_seconds=60.0)
    cache.add("hash1", "peer-a", now=0.0)
    cache.add("hash2", "peer-b", now=0.0)
    cache.add("hash3", "peer-c", now=0.0)
    assert cache.has("hash1", now=1.0) is False
    assert cache.has("hash3", now=1.0) is True


def test_cache_expires_entries() -> None:
    cache = RelaySeenCache(max_entries=10, ttl_seconds=10.0)
    cache.add("hash1", "peer-a", now=0.0)
    assert cache.has("hash1", now=15.0) is False
