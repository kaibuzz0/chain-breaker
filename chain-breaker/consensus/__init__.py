"""
Chain-Breaker Consensus Module
==============================

Hybrid consensus: PoW for blocks + PoA for scripture anchors.
"""

from .pow import PoWMiner
from .poa import PoAAuthority, PoAConsensus

__all__ = ['PoWMiner', 'PoAAuthority', 'PoAConsensus']
