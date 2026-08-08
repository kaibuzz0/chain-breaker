"""Rate limiting and resource-limit primitives for transport."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TransportLimits:
    """Resource limits enforced by a transport endpoint."""

    # Queue limits
    max_inbound_queue_depth: int = 128
    max_outbound_queue_depth: int = 128
    max_inbound_queue_bytes: int = 8_388_608  # 8 MiB
    max_outbound_queue_bytes: int = 8_388_608

    # Message rate limits (per window)
    max_messages_per_window: int = 1000
    max_bytes_per_window: int = 16_777_216  # 16 MiB
    window_seconds: float = 1.0

    # Outstanding flow limits
    max_pending_sends: int = 64
    max_pending_receives: int = 64

    # Connection / activity limits
    connect_timeout_seconds: float = 10.0
    receive_timeout_seconds: float = 30.0
    send_timeout_seconds: float = 30.0
    idle_timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.max_inbound_queue_depth <= 0:
            raise ValueError("max_inbound_queue_depth must be positive")
        if self.max_outbound_queue_depth <= 0:
            raise ValueError("max_outbound_queue_depth must be positive")
        if self.max_messages_per_window <= 0:
            raise ValueError("max_messages_per_window must be positive")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")


class RateLimiter:
    """Sliding-window rate limiter for messages and bytes."""

    def __init__(self, limits: TransportLimits) -> None:
        self._limits = limits
        self._message_times: deque[float] = deque()
        self._byte_windows: deque[tuple[float, int]] = deque()

    def check(self, message_count: int, byte_count: int, now: float | None = None) -> bool:
        """Return True if the operation is within limits, False otherwise."""
        if now is None:
            now = time.monotonic()

        window = self._limits.window_seconds
        cutoff = now - window

        # Drop old message timestamps
        while self._message_times and self._message_times[0] <= cutoff:
            self._message_times.popleft()

        # Drop old byte windows
        while self._byte_windows and self._byte_windows[0][0] <= cutoff:
            self._byte_windows.popleft()

        if (len(self._message_times) + message_count) > self._limits.max_messages_per_window:
            return False

        total_bytes = sum(b for _, b in self._byte_windows) + byte_count
        return total_bytes <= self._limits.max_bytes_per_window

    def record(self, message_count: int, byte_count: int, now: float | None = None) -> None:
        """Record a successful operation in the limiter."""
        if now is None:
            now = time.monotonic()

        for _ in range(message_count):
            self._message_times.append(now)
        if byte_count:
            self._byte_windows.append((now, byte_count))
