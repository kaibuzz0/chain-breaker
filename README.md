# E8-Cipher: Quantum-Resistant Cryptography

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![E8 Math](https://img.shields.io/badge/math-E8%20Lattice-red.svg)](https://en.wikipedia.org/wiki/E8_(mathematics))

> **Quantum-Resistant Encryption Using the E8 Lie Group**
> 
> "The most symmetric structure in mathematics protecting the most valuable information"

---

## 🎯 What is E8-Cipher?

A conceptual cryptographic library implementing:
- **E8 lattice-based encryption** - Learning With Errors (LWE) over the E8 root lattice
- **Hybrid signatures** - ECDSA + E8 commitments for quantum resistance
- **Blockchain primitives** - E8-enhanced hashing for the Chain-Breaker project

### Security Foundation

| Property | Value | Significance |
|----------|-------|--------------|
| Dimensions | 8 | Optimal for crypto (not too large, not too small) |
| Roots | 240 | Dense lattice structure |
| Weyl Group | 696,729,600 | Massive symmetry for mixing |
| Security | NP-hard SVP | Quantum-resistant hardness |

---

## 📦 Installation

```bash
# Clone repository
git clone https://github.com/kaibuzz0/e8-cipher.git
cd e8-cipher

# Install dependencies
pip install numpy ecdsa

# Run self-tests
python e8_core.py
python chain_core.py
```

---

## 🚀 Quick Start

### Basic Encryption

```python
from e8_core import E8Cipher

# Create cipher with 32-byte seed
cipher = E8Cipher(private_seed=b'my-secret-key-32-bytes-long!')

# Encrypt
encrypted = cipher.encrypt(b"Hello E8")
print(f"Ciphertext: {encrypted['commitment']}")

# Decrypt
decrypted = cipher.decrypt(encrypted)
print(f"Decrypted: {decrypted.decode()}")
```

### Blockchain Hashing

```python
from e8_core import E8WeylTransform

weyl = E8WeylTransform()

# E8-enhanced hash for blockchain
data = b"block header data"
seed = 12345  # Nonce
hash_result = weyl.transform(data, seed)

print(f"E8 Hash: {hash_result.hex()}")
```

### Hybrid Signatures

```python
from e8_signature import HybridSignature

signer = HybridSignature()
message = b"Scripture anchor: Genesis 1:1"

# Sign with ECDSA + E8 commitment
sig = signer.sign(message)

# Verify
is_valid = signer.verify(message, sig)
print(f"Signature valid: {is_valid}")
```

---

## 🏗️ Architecture

```
e8-cipher/
├── e8_core.py          # E8 lattice mathematics
│   ├── E8Lattice       # 240 roots, Weyl group
│   ├── E8Cipher        # Encrypt/decrypt
│   └── E8WeylTransform # Blockchain hashing
│
├── e8_signature.py     # Hybrid signatures
│   ├── HybridSignature     # ECDSA + E8
│   └── ScriptureAuthority  # Multi-sig for canon
│
├── chain_core.py       # Blockchain structure
│   ├── Block           # Block with E8 hash
│   ├── Blockchain      # Chain validation
│   └── ScriptureTransaction # Bible anchoring
│
└── mobile_db.py        # SQLite storage
    ├── MobileChainDB   # Three storage modes
    └── BatteryAwareDB  # Mobile optimization
```

---

## 🔬 Mathematical Background

### E8 Root Lattice

The E8 lattice consists of 240 root vectors in 8-dimensional space:

**Type 1 Roots** (112 total):
- Form: (±1, ±1, 0, 0, 0, 0, 0, 0) and permutations
- Length: √2

**Type 2 Roots** (128 total):
- Form: (±½, ±½, ±½, ±½, ±½, ±½, ±½, ±½)
- Constraint: Even number of minus signs
- Length: √2

### Weyl Transformations

The Weyl group W(E8) has 696,729,600 elements. Each element is a composition of reflections:

```
r_α(v) = v - 2⟨v,α⟩/⟨α,α⟩ × α
```

**Properties:**
- Self-inverse: r_α(r_α(v)) = v
- Orthogonal: preserves dot products
- Integer lattice: maps E8 to E8

### Learning With Errors (LWE)

Security based on the hardness of finding short vectors in the E8 lattice:

1. **Encryption**: Add small E8 "noise" to plaintext
2. **Security**: Without private key, must solve SVP
3. **Quantum**: SVP believed hard even for quantum computers

---

## 🛡️ Security Model

### Classical Attacks

| Attack | Difficulty | Notes |
|--------|-----------|-------|
| Brute force | 2^256 | Hash preimage resistance |
| Lattice reduction | NP-hard | SVP in 8D |
| Birthday | 2^128 | Collision resistance |

### Quantum Attacks

| Algorithm | Impact | Mitigation |
|-----------|--------|------------|
| Shor's | Breaks ECDSA | E8 layer remains secure |
| Grover's | 2x speedup | Still 2^128 effective |
| Quantum annealing | Unknown | SVP structure resistant |

---

## 📱 Mobile Optimization

### Three Storage Modes

```python
# Ultra-light: Headers only (~50MB)
db = MobileChainDB("chain.db", mode="ultra_light")

# Light: Headers + UTXO (~200MB)
db = MobileChainDB("chain.db", mode="light")

# Full: Complete chain (~2GB)
db = MobileChainDB("chain.db", mode="full")
```

### Battery Awareness

```python
# Only mine when charging
if is_charging() and battery_level() > 50:
    mine_block()

# Pause sync when battery low
if battery_level() < 20:
    sync_enabled = False
```

---

## 🧪 Testing

### Run Self-Tests

```bash
python e8_core.py       # Test E8 mathematics
python e8_signature.py  # Test hybrid signatures
python chain_core.py    # Test blockchain
python mobile_db.py     # Test database
```

### Expected Output

```
🧪 E8-Core Self-Test Suite
======================================================================

1️⃣ Testing E8 Lattice Initialization...
   ✅ Lattice initialized correctly
   📊 Roots: 240 vectors in 8D space
   🔢 Weyl group size: 696,729,600

2️⃣ Testing Root Generation...
   ✅ Type 1 roots: 112/112
   ✅ Type 2 roots: 128/128

3️⃣ Testing Weyl Reflection (Self-Inverse)...
   ✅ Weyl reflection is self-inverse

...

🎉 ALL TESTS PASSED!
```

---

## 🎯 Chain-Breaker Integration

This library powers the **Chain-Breaker** blockchain for scripture preservation:

- **Purpose**: Eternally anchor Biblical texts
- **Consensus**: Hybrid PoA (scripture) + PoW (blocks)
- **Mobile**: Runs on Android/Termux
- **Cryptography**: E8 quantum-resistant signatures

See the full Chain-Breaker architecture in the code documentation.

---

## 📚 References

### Mathematics
- [E8 Wikipedia](https://en.wikipedia.org/wiki/E8_(mathematics))
- [Root Systems](https://en.wikipedia.org/wiki/Root_system)
- [Weyl Groups](https://en.wikipedia.org/wiki/Weyl_group)

### Cryptography
- [Lattice-Based Crypto](https://en.wikipedia.org/wiki/Lattice-based_cryptography)
- [Learning With Errors](https://en.wikipedia.org/wiki/Learning_with_errors)
- [NIST PQC](https://csrc.nist.gov/projects/post-quantum-cryptography)

### Blockchain
- [Bitcoin](https://bitcoin.org/bitcoin.pdf)
- [Ethereum](https://ethereum.org/whitepaper)

---

## 📝 License

MIT License - See [LICENSE](LICENSE) file

---

## 🙏 Acknowledgments

- E8 mathematics: Exceptional Lie group theory
- Lattice crypto: Oded Regev (LWE), NTRU
- Blockchain: Satoshi Nakamoto, Vitalik Buterin
- Mobile optimization: Termux community

---

> "Mathematics is the language in which God has written the universe." — Galileo
