"""Transport abstraction layer for Chain-Breaker network protocol.

This package provides interfaces and primitives for moving validated network
messages between endpoints. It intentionally contains no sockets, no peers, no
discovery, and no consensus logic.

The only concrete transport in Phase 8C is the in-memory transport, used for
deterministic testing of the transport abstraction itself.
"""

from __future__ import annotations

from .connection import Connection, ConnectionState
from .errors import (
    TransportClosedError,
    TransportError,
    TransportLimitError,
    TransportStateError,
    TransportTimeoutError,
)
from .interface import Transport
from .limits import RateLimiter, TransportLimits
from .memory import MemoryTransport, create_memory_transport_pair
from .queue import BoundedMessageQueue

__all__ = [
    "Transport",
    "Connection",
    "ConnectionState",
    "TransportError",
    "TransportClosedError",
    "TransportLimitError",
    "TransportTimeoutError",
    "TransportStateError",
    "TransportLimits",
    "RateLimiter",
    "BoundedMessageQueue",
    "MemoryTransport",
    "create_memory_transport_pair",
]
