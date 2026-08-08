"""Relay-layer exceptions."""

from __future__ import annotations

from chainbreaker.network.errors import NetworkError


class RelayError(NetworkError):
    """Base class for relay-layer errors."""


class RelayInvalidBlockError(RelayError):
    """A block failed validation or structural checks."""


class RelayRateLimitError(RelayError):
    """A relay operation exceeded rate or resource limits."""


class RelayUnknownBlockError(RelayError):
    """A requested block is not available locally."""
