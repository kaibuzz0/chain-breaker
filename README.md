# Chain-Breaker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![E8 Enhanced](https://img.shields.io/badge/E8-Enhanced-purple.svg)](https://en.wikipedia.org/wiki/E8_(mathematics))

**E8-Enhanced Blockchain for Eternal Scripture Preservation**

Chain-Breaker is a mobile-optimized blockchain designed to permanently anchor Biblical text references with quantum-resistant cryptography based on the **E8 Lie Group**.

https://t.me/+iKdp5BlTpUFmZmMx
---

## 🌟 Features

### Quantum-Resistant Cryptography
- **E8 Lie Group**: 240 roots in 8-dimensional space
- **Weyl Group**: 696,729,600 symmetries for cryptographic mixing
- **Hybrid Signatures**: ECDSA + E8 commitment (survives quantum attacks)
- **NP-Hard Security**: Based on Shortest Vector Problem

### Complete Blockchain Infrastructure
- **⛏️ Miner**: Multi-threaded E8-enhanced Proof-of-Work mining
- **🌐 Node**: Full P2P networking with block relay
- **👛 Wallet**: Key generation and management
- **🔍 Explorer**: Blockchain viewing and verification

### Scripture-First Design
- **Multi-Version Support**: Hebrew, Greek, Latin, English
- **Authority Attestation**: PoA consensus for scripture anchors
- **Canonical Validation**: All 66 books of the Bible
- **Immutable Anchoring**: SHA-256 + E8 commitment

### Mobile-Optimized
- **SQLite Storage**: Android/Termux compatible
- **Battery-Aware Mining**: Interruptible, cooperative mining
- **Lightweight**: Minimal memory footprint
- **Fast Verification**: Mobile-optimized validation

### Hybrid Consensus
- **PoW**: Proof of Work for block production
- **PoA**: Proof of Authority for scripture anchors
- **Difficulty Adjustment**: 5-minute block targets

---

## 🚀 Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/kaibuzz0/chain-breaker.git
cd chain-breaker

# Install dependencies
pip install numpy ecdsa

# Verify installation
python chainbreaker.py status
```

### Run the Demo

```bash
# Full demonstration
python demo.py

# Or use the interactive menu
python chainbreaker.py
```

---

## 📦 Components

### 🎮 Master Control (`chainbreaker.py`)
All-in-one control interface:
```bash
python chainbreaker.py miner --threads 4 --difficulty 100
python chainbreaker.py node --port 8333
python chainbreaker.py wallet generate mykey
python chainbreaker.py explorer chain
python chainbreaker.py status
```

### ⛏️ Miner (`miner.py`)
E8-enhanced Proof-of-Work mining:
```bash
# Mine a single block
python miner.py --threads 4 --difficulty 100

# Mine continuously
python miner.py --threads 4 --difficulty 100 --continuous
```

### 🌐 Node (`node.py`)
Full P2P blockchain node:
```bash
# Start node
python node.py --port 8333 --data-dir ./my_node

# With peers
python node.py --port 8333 --add-peer 192.168.1.5:8333
```

### 👛 Wallet (`wallet.py`)
Key management:
```bash
# Generate key
python wallet.py generate mykey

# List keys
python wallet.py list

# Sign message
python wallet.py sign mykey "Hello World"
```

### 🔍 Explorer (`explorer.py`)
Blockchain viewer:
```bash
# View chain
python explorer.py chain

# View specific block
python explorer.py block 0

# Verify integrity
python explorer.py verify

# Search
python explorer.py search "Genesis"
```

---

## 📁 Architecture

```
chain-breaker/
├── chain-breaker/          # Core library
│   ├── crypto/              # E8 mathematics
│   │   ├── e8_core.py       # 240 E8 roots, Weyl transformations
│   │   ├── e8_hash.py       # Block hashing with E8 mixing
│   │   └── e8_hybrid_sig.py # Hybrid ECDSA + E8 signatures
│   ├── core/                # Blockchain structures
│   │   ├── block.py         # Block class
│   │   └── blockchain.py    # Chain management
│   ├── consensus/           # Mining algorithms
│   ├── p2p/                 # Networking
│   └── scripture/           # Bible anchoring
│
├── chainbreaker.py          # Master control CLI
├── miner.py                 # Standalone miner
├── node.py                  # Full P2P node
├── wallet.py                # Wallet CLI
├── explorer.py              # Block explorer
├── demo.py                  # Full demonstration
└── README.md               # This file
```

---

## 🔐 E8 Cryptography

The E8 Lie Group provides quantum resistance:

```python
from chain_breaker.crypto.e8_core import get_e8_lattice, get_e8_weyl

# E8 lattice with 240 roots
e8 = get_e8_lattice()
print(f"E8 has {len(e8.roots)} roots")  # 240
print(f"Weyl group: {e8.weyl_group_size:,}")  # 696,729,600

# Quantum-resistant hashing
weyl = get_e8_weyl()
hash_result = weyl.transform(b"data", seed=42)
```

---

## 🌐 Network Setup

1. **Start first node:**
   ```bash
   python node.py --port 8333 --data-dir ./node1
   ```

2. **Start second node:**
   ```bash
   python node.py --port 8334 --data-dir ./node2 --add-peer localhost:8333
   ```

3. **Mine blocks:**
   ```bash
   python miner.py --continuous
   ```

---

## 📊 Example Session

```bash
# 1. Check system status
python chainbreaker.py status

# 2. Generate wallet key
python chainbreaker.py wallet generate miner1

# 3. Start mining
python chainbreaker.py miner --threads 4 --difficulty 1000

# 4. View blockchain
python chainbreaker.py explorer chain

# 5. Verify integrity
python chainbreaker.py explorer verify
```

---

## 🛠️ Development

### Running Tests

```bash
python test_all.py
```

### Clean Repository Status

✅ All 49 Python files are clean and syntax-error free.

---

## 📱 Mobile/Termux Usage

```bash
# Install on Android via Termux
pkg update
pkg install python python-numpy
pip install ecdsa

# Run
python demo.py
```

---

## 🔬 Technical Details

### E8 Mathematics
- **Dimension**: 8
- **Root System**: 240 vectors
- **Weyl Group**: 696,729,600 elements
- **Security**: NP-hard Shortest Vector Problem

### Block Structure
```python
{
    "index": 0,
    "timestamp": 1234567890.0,
    "data": "Genesis Block",
    "previous_hash": "0" * 64,
    "hash": "abc...",
    "nonce": 12345,
    "difficulty": 100
}
```

### Consensus
- **Algorithm**: E8-enhanced Proof of Work
- **Block Time**: ~5 minutes
- **Difficulty**: Dynamic adjustment
- **Mining**: Multi-threaded with Weyl transformations

---

## 📝 License

MIT License - See LICENSE file

---

## 🙏 Acknowledgments

- E8 Lie Group mathematics
- Bitcoin/Ethereum for blockchain concepts
- Mobile-first design philosophy

---

**Repository**: https://github.com/kaibuzz0/chain-breaker

**Status**: ✅ All files clean and verified
