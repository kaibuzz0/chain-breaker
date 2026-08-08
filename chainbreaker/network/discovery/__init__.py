"""Peer discovery layer for Chain-Breaker.

This package implements the discovery models documented in Phase 8F:
peer records, a bounded peer table, bootstrap sources, and deterministic
connection-candidate selection.
"""

from chainbreaker.network.discovery.bootstrap import (
    BootstrapSource,
    MemoryBootstrapSource,
    StaticBootstrapSource,
)
from chainbreaker.network.discovery.discovery import DiscoveryManager
from chainbreaker.network.discovery.errors import DiscoveryError, PeerTableFullError
from chainbreaker.network.discovery.peer_table import PeerRecord, PeerSource, PeerStatus, PeerTable

__all__ = [
    "BootstrapSource",
    "DiscoveryError",
    "DiscoveryManager",
    "PeerRecord",
    "PeerSource",
    "PeerStatus",
    "PeerTable",
    "PeerTableFullError",
    "MemoryBootstrapSource",
    "StaticBootstrapSource",
]
