"""Errors specific to the socket transport layer."""

from __future__ import annotations

from chainbreaker.network.transport.errors import (
    TransportClosedError,
    TransportError,
    TransportLimitError,
)


class SocketTransportError(TransportError):
    """Base for socket transport failures."""


class SocketTransportLimitError(TransportLimitError):
    """Raised when socket-level resource limits are exceeded."""


class SocketClosedError(TransportClosedError):
    """Raised when operating on a closed socket."""
