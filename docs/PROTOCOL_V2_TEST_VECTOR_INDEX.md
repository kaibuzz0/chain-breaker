# Protocol v2 Test Vector Index

Version: `chainbreaker-scripture-v2`  
Branch: `registry-governance-hardening`  
Generated: final review phase

---

## 1. Genesis constants

| Constant | Value |
|----------|-------|
| `GENESIS_HASH` | `0000a6fd1e57aafd19da552440faa94803dbf1a1773bcd9af8ce3e0ae9fd13db` |
| `GENESIS_NONCE` | `42129` |
| `GENESIS_TIMESTAMP` | `1704067200` |
| `GENESIS_TARGET_HEX` | `0000ffff00000000000000000000000000000000000000000000000000000000` |
| `GENESIS_REGISTRY_ROOT` | `5814321ad489e630fef0350b1bff591d5cee8a821c00fa40a2cb2c99bd5b3186` |
| `GENESIS_THRESHOLD` | `2` |
| `GENESIS_GOVERNANCE_KEYS` | `[0000...0000, 1111...1111, 2222...2222]` (3 × 32-byte hex) |
| `NETWORK_ID` | `chainbreaker-scripture-v2` |
| `PROTOCOL_VERSION` | `2` |

### Genesis header bytes (149)

```hex
0202000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000005814321ad489e630fef0350b1bff591d5cee8a821c00fa40a2cb2c99bd5b318680009265000000000000ffff0000000000000000000000000000000000000000000000000000000091a4000000000000
```

Decodes to:

- type marker: `0x02`
- version: `2`
- prev_hash: `0000...0000`
- merkle_root: `0000...0000`
- registry_root: `5814321ad489e630fef0350b1bff591d5cee8a821c00fa40a2cb2c99bd5b3186`
- timestamp: `1704067200`
- target: `0000ffff00000000000000000000000000000000000000000000000000000000`
- nonce: `42129`

---

## 2. Empty registry state

| Value | Hex |
|-------|-----|
| Canonical bytes | `0100000019636861696e627265616b65722d7363726970747572652d7632030000000000000000000000000000000000000000000000000000000000000000111111111111111111111111111111111111111111111111111111111111111122222222222222222222222222222222222222222222222222222222222222220200` |
| SHA-256 root | `5814321ad489e630fef0350b1bff591d5cee8a821c00fa40a2cb2c99bd5b3186` |

Serialization layout:

- `governance_version` (4 bytes LE): `1`
- `network_id` (varint length + UTF-8): `chainbreaker-scripture-v2`
- `governance_keys` count (varint): `3`
- 3 × 32-byte governance keys
- `threshold` (1 byte): `2`
- records count (varint): `0`

---

## 3. Block header v2 layout

Total size: **149 bytes**

| Offset | Field | Size | Encoding |
|--------|-------|------|----------|
| 0 | type marker | 1 | `0x02` |
| 1 | version | 4 | uint32 LE |
| 5 | prev_hash | 32 | raw hex bytes |
| 37 | merkle_root | 32 | raw hex bytes |
| 69 | registry_root | 32 | raw hex bytes |
| 101 | timestamp | 8 | uint64 LE |
| 109 | target | 32 | raw hex bytes |
| 141 | nonce | 8 | uint64 LE |

Hash algorithm: `SHA256d(canonical_149_bytes)` interpreted as a big-endian 256-bit integer.

---

## 4. Proof of work rule

```text
valid iff:
    int(SHA256d(header_bytes), 16) <= target
```

Target encoding: 32-byte big-endian unsigned integer.

Chain work per block: `floor(MAX_TARGET / target)` where
`MAX_TARGET = 0x0000FFFF00000000000000000000000000000000000000000000000000000000`.

---

## 5. Governance transaction canonical encoding

Transactions are canonical JSON (sorted keys, `,`/`:` separators, no whitespace,
no NaN) and then SHA-256 hashed for transaction IDs and signature domains.

### Governance signature domain

```json
{
  "network_id": "chainbreaker-scripture-v2",
  "version": 2,
  "type": "registry",
  "body_hash": "<sha256-of-canonical-tx-body>"
}
```

### Attestation v2 domain

```json
{
  "network_id": "chainbreaker-scripture-v2",
  "version": 2,
  "type": "attestation",
  "body_hash": "<64-hex>",
  "curator_id": "<string>",
  "block_height": <int>
}
```

Example message hash (body=`a`*64, curator=`alice`, height=2):
`9dcdf90a7907b6ae8546b899097c25fbe0be5cc0a995510c41a3c6097ca91012`

---

## 6. Registry state transition rules

- `apply_registry_transaction(state, tx, height, txid, context)` is a pure function.
- `RegistryState` is immutable; every transition returns a new state.
- Records are sorted by `curator_id` UTF-8 bytes before serialization.
- A key is active at height `H` iff `activation_height <= H < revocation_height`
  (or `H >= activation_height` when not revoked).
- A transaction in block `H` must specify `activation_height > H`.

---

## 7. Compatibility notes

- v1 and v2 are separate networks.
- v2 headers use type marker `0x02`.
- v1 blocks are not accepted by v2 validation paths.
- No migration tool exists; a new network requires a new genesis.

---

## 8. Verification commands

```bash
python -m pytest -v
python -m pytest --cov=chainbreaker --cov-report=term-missing
python -m ruff check chainbreaker tests
python -m mypy chainbreaker
python -m build
python -m pip_audit -r requirements.txt
python -m bandit -r chainbreaker
```

All must pass.
