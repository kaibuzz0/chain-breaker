"""TCP socket transport for the Chain-Breaker network layer.

Phase 8E provides a real byte-stream transport over TCP sockets. It is the
first phase that uses real networking, but it intentionally does not include
peer discovery, gossip, synchronization, relay, mempool, or public node
operation.
"""

from __future__ import annotations

from .errors import SocketClosedError, SocketTransportError, SocketTransportLimitError
from .framing import EnvelopeFraming
from .limits import SocketLimits
from .socket_connection import SocketConnection, SocketConnectionState
from .tcp_transport import TCPClientTransport, TCPServerTransport

__all__ = [
    "EnvelopeFraming",
    "SocketConnection",
    "SocketConnectionState",
    "SocketLimits",
    "SocketClosedError",
    "SocketTransportError",
    "SocketTransportLimitError",
    "TCPClientTransport",
    "TCPServerTransport",
]
