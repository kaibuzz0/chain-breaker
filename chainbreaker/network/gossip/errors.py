"""Gossip-layer exceptions."""

from __future__ import annotations

from chainbreaker.network.errors import NetworkError


class GossipError(NetworkError):
    """Base class for gossip-layer errors."""


class GossipRateLimitError(GossipError):
    """A gossip message exceeded a rate or size limit."""
