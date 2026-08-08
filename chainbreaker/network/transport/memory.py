"""In-memory transport implementation for deterministic testing."""

from __future__ import annotations

import time
from typing import Any

from chainbreaker.network.envelope import NetworkEnvelope, parse_envelope, serialize_envelope

from .connection import Connection, ConnectionState
from .errors import TransportClosedError, TransportLimitError
from .interface import Transport
from .limits import RateLimiter, TransportLimits
from .queue import BoundedMessageQueue


class MemoryTransport(Transport):
    """A transport backed by a pair of asyncio queues.

    This is not a real network transport; it simulates a full-duplex byte pipe
    between two endpoints for deterministic testing of the transport layer.
    """

    def __init__(
        self,
        connection: Connection,
        limits: TransportLimits,
        outbound: BoundedMessageQueue,
        inbound: BoundedMessageQueue,
        peer: MemoryTransport | None = None,
    ) -> None:
        self._connection = connection
        self._limits = limits
        self._outbound = outbound
        self._inbound = inbound
        self._peer = peer
        self._rate_limiter = RateLimiter(limits)
        self._closed = False
        self._last_activity = time.monotonic()

    @property
    def is_open(self) -> bool:
        return (
            not self._closed
            and self._connection.state in {ConnectionState.OPENING, ConnectionState.ACTIVE}
        )

    async def send(self, envelope: NetworkEnvelope) -> None:
        self._connection.ensure_open()
        if self._closed:
            raise TransportClosedError("transport is closed")

        raw = serialize_envelope(envelope.message_type, envelope.flags, envelope.payload)
        if not self._rate_limiter.check(1, len(raw)):
            raise TransportLimitError("rate limit exceeded")

        await self._outbound.put(raw, timeout=self._limits.send_timeout_seconds)
        self._rate_limiter.record(1, len(raw))
        self._bump_activity()

    async def receive(self) -> NetworkEnvelope:
        self._connection.ensure_open()
        if self._closed:
            raise TransportClosedError("transport is closed")

        raw = await self._inbound.get(timeout=self._limits.receive_timeout_seconds)
        self._bump_activity()
        return parse_envelope(raw)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._inbound.close()
        self._outbound.close()
        self._connection.transition_to(ConnectionState.CLOSED)
        if self._peer is not None and not self._peer._closed:
            await self._peer.close()

    async def status(self) -> dict[str, Any]:
        inbound = self._inbound.metrics()
        outbound = self._outbound.metrics()
        return {
            "connection_id": self._connection.connection_id,
            "state": self._connection.state.name,
            "open": self.is_open,
            "inbound": {
                "depth": inbound.depth,
                "bytes_used": inbound.bytes_used,
                "capacity": inbound.capacity,
                "bytes_capacity": inbound.bytes_capacity,
                "drops": inbound.drops,
            },
            "outbound": {
                "depth": outbound.depth,
                "bytes_used": outbound.bytes_used,
                "capacity": outbound.capacity,
                "bytes_capacity": outbound.bytes_capacity,
                "drops": outbound.drops,
            },
        }

    def _bump_activity(self) -> None:
        self._last_activity = time.monotonic()

    def check_idle(self, now: float | None = None) -> bool:
        """Return True if the connection has exceeded the idle timeout."""
        if now is None:
            now = time.monotonic()
        if self._limits.idle_timeout_seconds <= 0:
            return False
        return (now - self._last_activity) > self._limits.idle_timeout_seconds


def create_memory_transport_pair(
    connection_id_a: str = "a",
    connection_id_b: str = "b",
    limits: TransportLimits | None = None,
) -> tuple[MemoryTransport, MemoryTransport]:
    """Create a pair of connected in-memory transports.

    Messages sent on one side are received on the other.
    """
    if limits is None:
        limits = TransportLimits()

    a_to_b = BoundedMessageQueue(limits.max_outbound_queue_depth, limits.max_outbound_queue_bytes, "a->b")
    b_to_a = BoundedMessageQueue(limits.max_inbound_queue_depth, limits.max_inbound_queue_bytes, "b->a")

    conn_a = Connection(connection_id_a)
    conn_b = Connection(connection_id_b)

    transport_a = MemoryTransport(conn_a, limits, a_to_b, b_to_a, peer=None)
    transport_b = MemoryTransport(conn_b, limits, b_to_a, a_to_b, peer=transport_a)
    transport_a._peer = transport_b

    conn_a.transition_to(ConnectionState.OPENING)
    conn_b.transition_to(ConnectionState.OPENING)
    conn_a.transition_to(ConnectionState.ACTIVE)
    conn_b.transition_to(ConnectionState.ACTIVE)

    return transport_a, transport_b
