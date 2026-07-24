# Chain-Breaker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

**E8-Enhanced Blockchain for Eternal Scripture Preservation**

Chain-Breaker is a mobile-optimized blockchain designed to permanently anchor Biblical text references with quantum-resistant cryptography based on the **E8 Lie Group**.

---

## 🌟 Features

### Quantum-Resistant Cryptography
- **E8 Lie Group**: 240 roots in 8-dimensional space
- **Weyl Group**: 696,729,600 symmetries for cryptographic mixing
- **Hybrid Signatures**: ECDSA + E8 commitment (survives quantum attacks)
- **NP-Hard Security**: Based on Shortest Vector Problem

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

## 📁 Architecture

```
chain-breaker/
├── chain-breaker/
│   ├── crypto/          # E8 mathematics & cryptography
│   │   ├── e8_core.py      # 240 E8 roots, Weyl transformations
│   │   ├── e8_hash.py      # E8-enhanced block hashing
│   │   └── e8_hybrid_sig.py # Hybrid ECDSA + E8 signatures
│   ├── core/            # Blockchain data structures
│   │   ├── block.py        # Block class
│   │   └── blockchain.py   # Blockchain with SQLite
│   ├── consensus/       # Mining & validation
│   │   ├── pow.py          # Proof of Work
│   │   └── poa.py          # Proof of Authority
│   ├── scripture/       # Bible anchoring
│   │   ├── reference.py    # Scripture references
│   │   ├── validator.py    # Canonical validation
│   │   └── authority.py    # Authority management
│   └── tests/           # Unit tests
├── demo.py              # Working demonstration
└── README.md           # This file
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- NumPy (`pip install numpy`)

### Installation

```bash
# Clone the repository
git clone https://github.com/kaibuzz0/chain-breaker.git
cd chain-breaker

# Run the demo
python demo.py
```

### Using the Blockchain

```python
from chain_breaker.core import Blockchain
from chain_breaker.scripture import ScriptureReference

# Create blockchain
bc = Blockchain()

# Add regular block
bc.add_block("Hello, World!", mine=True)

# Anchor scripture
ref = ScriptureReference.from_string("John 3:16")
bc.add_block(f"Scripture: {ref.to_string()}", mine=True)

# Validate chain
print(f"Chain valid: {bc.validate_chain()}")
print(f"Blocks: {len(bc.chain)}")
```

---

## 🧮 E8 Mathematical Foundation

### The E8 Lie Group
The largest exceptional Lie group:
- **Rank**: 8
- **Root System**: 240 vectors in ℝ⁸
- **Weyl Group**: 696,729,600 symmetries
- **Dimension**: 248 (as Lie algebra)

### Root System
```
Type 1 (112 roots): (±1, ±1, 0, 0, 0, 0, 0, 0) permutations
Type 2 (128 roots): (±½, ..., ±½) with even number of minuses
Total: 240 roots
```

### Weyl Reflection
```
s_α(v) = v - ⟨v,α⟩ α
```
**Key property**: Self-inverse (applying twice returns original)

---

## ⛏️ Mining

### Start Mining
```python
from chain_breaker.core import Blockchain

bc = Blockchain()
block = bc.add_block("My data", mine=True)
print(f"Mined block #{block.index} with nonce {block.nonce}")
```

### Mobile-Optimized
```python
from chain_breaker.consensus import MobileMiningManager

manager = MobileMiningManager()
if manager.can_mine():  # Checks battery
    result = manager.start_mining(block_data, difficulty)
```

---

## 📜 Scripture Anchoring

### Create Scripture Reference
```python
from chain_breaker.scripture import ScriptureReference, Version

# Single verse
ref = ScriptureReference.from_string("Genesis 1:1")

# Verse range
ref = ScriptureReference(
    book="John",
    chapter=3,
    verse_start=16,
    verse_end=17,
    version=Version.ENGLISH_KJV
)
```

### Validate Scripture
```python
from chain_breaker.scripture import ScriptureValidator

validator = ScriptureValidator()
is_valid, error = validator.validate_reference(ref)
```

---

## 🧪 Testing

```bash
# Run unit tests
python -m pytest chain-breaker/tests/

# Or run specific test
python chain-breaker/tests/test_core.py
```

---

## 📱 Termux/Android Deployment

```bash
# Install Termux from F-Droid
pkg update
pkg install python git
pip install numpy

git clone https://github.com/kaibuzz0/chain-breaker.git
cd chain-breaker
python demo.py
```

---

## 🔒 Security

- **Quantum-Resistant**: E8 lattice security (NP-hard SVP)
- **Hybrid Signatures**: ECDSA for speed, E8 for quantum resistance
- **Immutable Chain**: E8-enhanced SHA-256 hashing
- **Authority System**: Only authorized entities anchor scripture

---

## 🛠️ Development

### Project Structure
- **crypto/**: E8 mathematics (240 roots, Weyl transformations)
- **core/**: Blockchain classes (Block, Blockchain)
- **consensus/**: PoW/PoA hybrid consensus
- **scripture/**: Bible anchoring and validation
- **tests/**: Unit tests for all modules

### Adding Features
```python
# Example: Add new consensus mechanism
from chain_breaker.consensus import PoWMiner

class CustomMiner(PoWMiner):
    def custom_mining(self, block_data):
        # Your implementation
        pass
```

---

## 📄 License

MIT License - See [LICENSE](LICENSE)

---

## 🙏 Acknowledgments

- **E8 Mathematics**: Based on the exceptional Lie group E8
- **Bitcoin**: PoW inspiration
- **Scripture**: King James Version (public domain)

---

## 📞 Contact

- **GitHub**: [kaibuzz0/chain-breaker](https://github.com/kaibuzz0/chain-breaker)
- **Issues**: Open an issue for bugs or feature requests

---

**Built with ❤️ for eternal Scripture preservation**
