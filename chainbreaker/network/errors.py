"""Network layer exceptions."""

from __future__ import annotations


class NetworkError(Exception):
    """Base class for network-layer errors."""


class NetworkValidationError(NetworkError):
    """Raised when an envelope or payload fails validation."""


class PayloadHashMismatchError(NetworkValidationError):
    """Raised when the payload hash does not match the recomputed hash."""


class UnknownMessageTypeError(NetworkValidationError):
    """Raised when the message type byte is not a known V1 type."""


class OversizedPayloadError(NetworkValidationError):
    """Raised when the declared payload length exceeds MAX_PAYLOAD_BYTES."""
