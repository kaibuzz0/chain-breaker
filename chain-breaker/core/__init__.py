"""
Chain-Breaker Core Module
==========================

Blockchain data structures and chain management.
"""

from .block import Block, BlockValidator
from .blockchain import Blockchain, ChainConfig, create_genesis_block

__all__ = [
    'Block',
    'BlockValidator',
    'Blockchain',
    'ChainConfig',
    'create_genesis_block'
]
