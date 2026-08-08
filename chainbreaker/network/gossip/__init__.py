"""Gossip layer for Chain-Breaker.

This package implements bounded message propagation over established peer
connections. V1 gossip is limited to liveness (PING/PONG) and peer exchange
(PEX) announcements.
"""

from chainbreaker.network.gossip.cache import GossipCache
from chainbreaker.network.gossip.engine import GossipEngine, GossipLimits
from chainbreaker.network.gossip.errors import GossipError, GossipRateLimitError

__all__ = [
    "GossipCache",
    "GossipEngine",
    "GossipError",
    "GossipLimits",
    "GossipRateLimitError",
]
