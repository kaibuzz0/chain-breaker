"""
Chain-Breaker: Blockchain Microparts

A minimal, modular blockchain for eternal scripture preservation.

Features:
    - Mobile-optimized (Termux/Android compatible)
    - E8-enhanced cryptography (quantum-resistant)
    - Scripture anchoring (multi-version canonical support)
    - Hybrid consensus (PoA for scripture, PoW for blocks)

Quick Start:
    from chain_breaker import Wallet, Ledger
    
    wallet = Wallet.generate()
    ledger = Ledger()
    ledger.add_transaction({"from": wallet.address, ...})
    ledger.mine_pending("miner_address")
"""

__version__ = "0.2.0-e8"
__author__ = "Chain-Breaker Team"

# Don't auto-import heavy modules to keep import fast
# Users should import specific modules as needed
