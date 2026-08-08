from __future__ import annotations

import time

from chainbreaker.network.transport import RateLimiter, TransportLimits


def test_rate_limiter_accepts_under_limit() -> None:
    limits = TransportLimits(
        max_messages_per_window=10,
        max_bytes_per_window=10_000,
        window_seconds=1.0,
    )
    limiter = RateLimiter(limits)
    now = time.monotonic()
    assert limiter.check(5, 1000, now=now)


def test_rate_limiter_rejects_excess_messages() -> None:
    limits = TransportLimits(
        max_messages_per_window=5,
        max_bytes_per_window=10_000,
        window_seconds=1.0,
    )
    limiter = RateLimiter(limits)
    now = time.monotonic()
    assert not limiter.check(6, 100, now=now)


def test_rate_limiter_rejects_excess_bytes() -> None:
    limits = TransportLimits(
        max_messages_per_window=1000,
        max_bytes_per_window=100,
        window_seconds=1.0,
    )
    limiter = RateLimiter(limits)
    now = time.monotonic()
    assert not limiter.check(1, 101, now=now)


def test_rate_limiter_window_slides() -> None:
    limits = TransportLimits(
        max_messages_per_window=1,
        max_bytes_per_window=10_000,
        window_seconds=0.1,
    )
    limiter = RateLimiter(limits)
    now = time.monotonic()
    assert limiter.check(1, 1, now=now)
    limiter.record(1, 1, now=now)
    assert not limiter.check(1, 1, now=now)
    assert limiter.check(1, 1, now=now + 0.2)


def test_rate_limiter_records_and_checks() -> None:
    limits = TransportLimits(
        max_messages_per_window=2,
        max_bytes_per_window=1000,
        window_seconds=1.0,
    )
    limiter = RateLimiter(limits)
    now = time.monotonic()
    assert limiter.check(2, 500, now=now)
    limiter.record(2, 500, now=now)
    assert not limiter.check(1, 1, now=now)
