"""
chain_breaker/crypto/

Cryptographic primitives for Chain-Breaker blockchain.

Modules:
    e8_core: E8 Lie group mathematical foundation
    e8_hybrid_sig: Hybrid ECDSA + E8 signatures (quantum-resistant)
    e8_hash: E8-enhanced block hashing

Design Principles:
    - Modular: Use only what you need
    - Fast: ECDSA for speed, E8 for security
    - Future-proof: Quantum resistance built-in
    - Mobile: Optimized for resource constraints
"""

from .e8_core import (
    E8Lattice,
    E8WeylTransform,
    get_e8_lattice,
    get_e8_weyl
)

from .e8_hybrid_sig import (
    HybridSignature,
    E8Commitment,
    HybridSigner,
    ScriptureAuthoritySigner,
    MobileVerifier
)

from .e8_hash import (
    E8BlockHasher,
    DifficultyCalculator,
    MobileOptimizedMining
)

__all__ = [
    # E8 Core
    "E8Lattice",
    "E8WeylTransform",
    "get_e8_lattice",
    "get_e8_weyl",
    
    # Signatures
    "HybridSignature",
    "E8Commitment",
    "HybridSigner",
    "ScriptureAuthoritySigner",
    "MobileVerifier",
    
    # Hashing
    "E8BlockHasher",
    "DifficultyCalculator",
    "MobileOptimizedMining",
]
