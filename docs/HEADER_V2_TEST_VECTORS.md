# Header v2 Fixed Test Vectors

Version: `chainbreaker-scripture-v2`  
Status: **design vectors; must be recomputed after implementation**

This document provides fixed test vectors for the canonical v2 serialization
and commitments.  Some vectors are computed from the current reducer
implementation; others are structural templates that must be recomputed once
`RegistryState.genesis()` and the v2 header codec are implemented.

---

## 1. Empty registry state root

Computed from the current `chainbreaker.registry_state` implementation in a
fresh Python process.

### Inputs

```python
from chainbreaker.registry_state import RegistryState, registry_root, serialize_registry_state
empty = RegistryState.empty()
```

### Canonical bytes

```text
empty_registry_bytes_hex = 0100000019636861696e627265616b65722d7363726970747572652d763200
empty_registry_byte_length = 31
```

Breakdown:

| Bytes | Meaning |
|---|---|
| `01000000` | governance version = 1 (uint32 LE) |
| `19` | network ID length = 25 (varint) |
| `636861696e627265616b65722d7363726970747572652d7632` | UTF-8 `chainbreaker-scripture-v2` |
| `00` | curator record count = 0 |

### Root

```text
empty_registry_root = ea949b131c480ca88ce72caaf98d8b0e6f2b7e43b76e877a884299b9b0aa2c91
```

The root is the single SHA-256 of the canonical bytes above.

### Verification

```python
import hashlib
expected = hashlib.sha256(bytes.fromhex("0100000019636861696e627265616b65722d7363726970747572652d763200")).hexdigest()
assert expected == "ea949b131c480ca88ce72caaf98d8b0e6f2b7e43b76e877a884299b9b0aa2c91"
```

---

## 2. Genesis registry state (structural template)

This vector is a template.  The exact bytes and root must be recomputed after
`RegistryState.genesis(governance_keys, threshold)` is implemented.

### Genesis governance keys

These are deterministic placeholder keys.  A real network must replace them
with actual Ed25519 public keys and document the replacement as a protocol
constant.

```text
key_1 = 0000000000000000000000000000000000000000000000000000000000000000
key_2 = 1111111111111111111111111111111111111111111111111111111111111111
key_3 = 2222222222222222222222222222222222222222222222222222222222222222
threshold = 2
```

### Expected genesis registry structure

```text
RegistryState(
    governance_version = 1,
    network_id = "chainbreaker-scripture-v2",
    governance_keys = [key_1, key_2, key_3],  # sorted lexicographically
    threshold = 2,
    curators = [],
)
```

### Root formula

```text
genesis_registry_root = SHA-256(canonical_serialization(genesis_registry_state))
```

The canonical serialization must include:

- governance version
- network ID
- governance key count
- each governance key as 32 raw bytes
- threshold as uint8
- curator record count

---

## 3. V2 genesis header (structural template)

A v2 genesis header with no transactions.

### Header fields

```text
version = 2
prev_hash = 0000000000000000000000000000000000000000000000000000000000000000
merkle_root = 0000000000000000000000000000000000000000000000000000000000000000
registry_root = <genesis_registry_root from section 2>
timestamp = 1704067200
target = 0000ffff00000000000000000000000000000000000000000000000000000000
nonce = <computed by brute force>
```

### Canonical byte layout

```text
offset 0:   type marker        1 byte   0x01
offset 1:   version            4 bytes  uint32 LE
offset 5:   prev_hash          32 bytes
offset 37:  merkle_root        32 bytes
offset 69:  registry_root      32 bytes
offset 101: timestamp          8 bytes  uint64 LE
offset 109: target             32 bytes
offset 141: nonce              8 bytes  uint64 LE
```

Total header size: 149 bytes.

### Hash formula

```text
genesis_hash = SHA-256(SHA-256(header_bytes))
```

The genesis nonce must be recomputed to satisfy:

```text
int(genesis_hash, 16) <= int(target, 16)
```

---

## 4. Sample v2 block header (non-genesis)

### Header fields

```text
version = 2
prev_hash = 0000000000000000000000000000000000000000000000000000000000000001
merkle_root = abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefab
registry_root = ea949b131c480ca88ce72caaf98d8b0e6f2b7e43b76e877a884299b9b0aa2c91
timestamp = 1704067201
target = 0000ffff00000000000000000000000000000000000000000000000000000000
nonce = 123456789
```

### Expected canonical bytes (hex)

```text
02                                      # type marker
02000000                                # version = 2 LE
0000000000000000000000000000000000000000000000000000000000000001  # prev_hash
abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefab      # merkle_root
<registry_root 32 bytes>                # ea949b...
0100000000000000                        # timestamp = 1704067201 LE
0000ffff00000000000000000000000000000000000000000000000000000000  # target
15cd5b0700000000                        # nonce = 123456789 LE
```

### Hash

```text
header_hash = SHA-256(SHA-256(header_bytes))
```

This vector must be recomputed with the exact codec implementation.

---

## 5. Valid curator registration transaction (structural template)

### Transaction body

```json
{
  "schema_version": 1,
  "network_id": "chainbreaker-scripture-v2",
  "action": "curator_register",
  "curator_id": "alpha",
  "public_key_hex": "<32-byte Ed25519 public key hex>",
  "activation_height": 5,
  "previous_registry_root": "<root of state before this tx>",
  "display_metadata_hash": null
}
```

### Governance signatures

The body is signed by at least `threshold` genesis governance keys.  Each
signature covers:

```text
SHA-256(canonical_json({
    "network_id": "chainbreaker-scripture-v2",
    "version": 2,
    "type": "registry",
    "body_hash": SHA-256(canonical_json(body_without_witnesses))
}))
```

### Transaction ID

```text
txid = SHA-256(SHA-256(canonical_transaction_bytes))
```

---

## 6. Valid rotation transaction (structural template)

### Transaction body

```json
{
  "schema_version": 1,
  "network_id": "chainbreaker-scripture-v2",
  "action": "curator_rotate",
  "curator_id": "alpha",
  "public_key_hex": "<old 32-byte public key hex>",
  "new_public_key_hex": "<new 32-byte public key hex>",
  "activation_height": 10,
  "previous_registry_root": "<root of state before this tx>",
  "display_metadata_hash": null
}
```

### Signatures

- Governance signatures: threshold count from current registry state.
- Curator signature: signature by the old active key over the same message.

---

## 7. Valid revocation transaction (structural template)

### Transaction body

```json
{
  "schema_version": 1,
  "network_id": "chainbreaker-scripture-v2",
  "action": "curator_revoke",
  "curator_id": "alpha",
  "public_key_hex": "<active 32-byte public key hex>",
  "revocation_height": 20,
  "reason_code": "compromise",
  "previous_registry_root": "<root of state before this tx>"
}
```

### Signatures

- Governance signatures: threshold count from current registry state.
- Curator signature: signature by the active key over the same message.

---

## 8. Invalid post-revocation attestation

A transaction at height `H = 20` signed by `alpha`'s old key after revocation
at height 20 must fail historical validation.

### Validation rule

```text
curator_key_at(State(B[0..19]), "alpha", 20) = None
signature_key != None
==> invalid attestation
```

---

## 9. Verification requirements

Every vector in this document must pass two tests:

1. **In-process recomputation.**  A unit test imports the project modules and
   recomputes the vector in the same process.

2. **Fresh-process recomputation.**  A subprocess starts a new Python
   interpreter, imports only the required modules, and recomputes the vector.

The two results must match exactly.

---

## 10. Open vectors pending implementation

| Vector | Blocked by |
|---|---|
| Exact genesis registry root | `RegistryState.genesis()` not implemented |
| Exact genesis header hash | header v2 codec not implemented; nonce not mined |
| Exact sample block header hash | header v2 codec not implemented |
| Exact governance transaction IDs | governance transaction serialization in transaction wrapper |
| Exact valid/invalid attestation vectors | historical validation in `witness.py` not implemented |

These vectors will be filled in during Milestone 4 and recomputed in two
fresh processes before the milestone is committed.
