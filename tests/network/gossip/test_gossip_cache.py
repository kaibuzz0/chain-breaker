from __future__ import annotations

import time

from chainbreaker.network.gossip import GossipCache


def test_cache_rejects_duplicates() -> None:
    cache = GossipCache()
    assert cache.seen(1, b"hello") is False
    cache.add(1, b"hello")
    assert cache.seen(1, b"hello") is True


def test_cache_distinguishes_message_types() -> None:
    cache = GossipCache()
    cache.add(1, b"hello")
    assert cache.seen(2, b"hello") is False


def test_cache_expires_entries() -> None:
    cache = GossipCache(ttl_seconds=0.01)
    cache.add(1, b"hello")
    assert cache.seen(1, b"hello") is True
    time.sleep(0.02)
    assert cache.seen(1, b"hello") is False


def test_cache_bounded() -> None:
    cache = GossipCache(max_entries=2)
    cache.add(1, b"a")
    cache.add(2, b"b")
    cache.add(3, b"c")
    assert cache.size <= 2
