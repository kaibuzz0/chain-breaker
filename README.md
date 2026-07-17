# Chain-Breaker: Blockchain Microparts

Minimal, modular blockchain primitives for dense deployment.

## Purpose

This is a **conceptual implementation** of blockchain microparts:
- Educational foundation
- Mobile-optimized (Termux/Android)
- Composable components
- Starting point for full blockchain

## Components

| Module | Purpose | Lines |
|--------|---------|-------|
| `hash_engine` | SHA256, Double-SHA256, Merkle trees | ~150 |
| `block_core` | Block structure, mining, validation | ~200 |
| `chain_ledger` | Chain management, UTXO | ~220 |
| `wallet_key` | Key generation, signing | ~180 |

## Quick Start

```python
from chain_breaker import Wallet, Ledger

# Create wallet
wallet = Wallet.generate()

# Create ledger
ledger = Ledger()

# Add transaction
ledger.add_transaction({
    "from": wallet.address,
    "to": "recipient",
    "amount": 50
})

# Mine
ledger.mine_pending("miner_address")
```

## Demo

```bash
cd /root/chain-breaker
python3 demo.py
```

## Design

- **Micro**: Each module <500 lines
- **Dense**: Maximum functionality per line  
- **Mobile**: Optimized for resource constraints
- **Composable**: Mix-and-match parts

## Status

Conceptual v0.1.0 — Educational foundation.

Not production-ready:
- No networking
- Basic consensus
- No persistence
- Simplified crypto

## Next Steps

- p2p_mesh: Peer-to-peer communication
- consensus_v1: Full consensus rules
- pow_miner: Production mining
- persistence: Database storage

## License

MIT — For research and educational use.
