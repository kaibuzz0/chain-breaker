"""Discovery-layer exceptions."""

from __future__ import annotations

from chainbreaker.network.errors import NetworkError


class DiscoveryError(NetworkError):
    """Base class for discovery-layer errors."""


class PeerTableFullError(DiscoveryError):
    """The peer table has reached its capacity limit."""
