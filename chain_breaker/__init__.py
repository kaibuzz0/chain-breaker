"""
Chain-Breaker: Conceptual Blockchain Microparts

Minimal, modular blockchain primitives designed for dense mobile deployment.
Each component is self-contained and can run independently or composed into larger systems.

Design Philosophy:
- Micro: Each module <500 lines, single responsibility
- Dense: Maximum functionality per line
- Mobile-First: Optimized for Termux/Android resource constraints
- Composable: Mix-and-match components

Core Components:
- hash_engine: Cryptographic primitives (SHA256, Merkle trees)
- block_core: Block structure and validation
- chain_ledger: Append-only ledger with integrity checks
- p2p_mesh: Minimal peer-to-peer communication
- pow_miner: Proof-of-work mining (conceptual)
- wallet_key: Key generation and management
- consensus_v1: Simple consensus rules
"""

__version__ = "0.1.0-concept"
__author__ = "kaibuzz0"

from .hash_engine import HashEngine, MerkleTree
from .block_core import Block, BlockHeader
from .chain_ledger import Ledger
from .wallet_key import Wallet

__all__ = [
    "HashEngine",
    "MerkleTree", 
    "Block",
    "BlockHeader",
    "Ledger",
    "Wallet",
]
