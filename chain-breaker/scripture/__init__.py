"""
Chain-Breaker Scripture Anchoring Module
=========================================

Permanently anchor Biblical text on the blockchain.
- Multi-version support (Hebrew, Greek, Latin, English)
- Authority attestation (PoA consensus)
- Immutable scripture references
"""

from .reference import ScriptureReference, ScriptureAnchor
from .validator import ScriptureValidator, Version
from .authority import AuthorityManager

__all__ = [
    'ScriptureReference',
    'ScriptureAnchor', 
    'ScriptureValidator',
    'Version',
    'AuthorityManager'
]
