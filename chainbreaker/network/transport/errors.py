"""Transport-layer exceptions."""

from __future__ import annotations


class TransportError(Exception):
    """Base class for transport-layer errors."""


class TransportClosedError(TransportError):
    """Raised when an operation is attempted on a closed transport."""


class TransportLimitError(TransportError):
    """Raised when a transport limit is exceeded."""


class TransportTimeoutError(TransportError):
    """Raised when a transport operation exceeds its timeout."""


class TransportStateError(TransportError):
    """Raised for invalid connection state transitions."""
