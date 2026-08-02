# Adversarial Serialization Review

Phase: **5A  Canonical Serialization Attack Testing**  
Branch: `registry-governance-hardening`  
Status: design-only before code changes

---

## Goal

Find whether the protocol has more than one canonical byte representation for
any consensus object.  If multiple byte sequences decode to the same logical
value, attackers can create divergent hashes, signatures, or state roots.

---

## Attack model

We assume a malicious or buggy participant controls the raw bytes sent to any
decoder.  The decoder must:

1. Accept exactly the canonical byte sequence for each valid object.
2. Reject every non-canonical or malformed sequence deterministically.
3. Never produce two different hashes for the same logical object.

---

## Targets

### 1. BlockHeaderV2

Path: `chainbreaker/codec.py` (`encode_header_v2` / `decode_header_v2`)

Canonical form: exactly 149 bytes.

| Field | Size | Encoding | Canonical rule |
|-------|------|----------|----------------|
| type marker | 1 | raw byte | must be `0x02` |
| version | 4 | uint32 LE | no padding alternatives |
| prev_hash | 32 | raw 32 bytes | lowercase hex only in JSON, raw in bytes |
| merkle_root | 32 | raw 32 bytes | same |
| registry_root | 32 | raw 32 bytes | same |
| timestamp | 8 | uint64 LE | no signed interpretation |
| target | 32 | raw 32 bytes | big-endian value inside header |
| nonce | 8 | uint64 LE | no signed interpretation |

Attack vectors:

- Extra trailing bytes after the 149-byte header.
- Missing bytes.
- Wrong type marker (`0x01`, `0x03`, `0x00`).
- Reordered fields.
- Big-endian version/timestamp/nonce (wrong endianness).
- Oversized varints (N/A for fixed layout, but still tested).
- Negative version/timestamp/nonce via signed interpretation.
- Zero-length hashes or non-32-byte hash fields.

Expected behavior: `CodecError` or `False` from validation.

### 2. RegistryState

Path: `chainbreaker/registry_state.py` (`serialize_registry_state`)

Canonical form: byte sequence produced by `serialize_registry_state`.

Components:

- `governance_version` (4 bytes LE)
- `network_id` (varint length + UTF-8)
- `governance_keys` count (varint) + 3×32 bytes
- `threshold` (1 byte)
- records count (varint) + serialized records

Record serialization:

- record schema version (4 bytes LE)
- curator_id (varint length + UTF-8)
- public_key (32 bytes)
- activation_height (8 bytes LE)
- revocation sentinel (8 bytes LE, `0xFF..FF` for unrevoked)
- previous_key (32 bytes, zeros if none)
- registration_txid (32 bytes)
- latest_rotation_txid (32 bytes, zeros if none)

Attack vectors:

- Reordered records.
- Reordered governance keys.
- Duplicate curator IDs.
- Duplicate governance keys.
- Invalid varint encoding.
- Truncated record fields.
- Extra bytes after state.
- Different revocation sentinel values.
- Mutable `records` tuple (Python object identity).

Expected behavior: non-canonical bytes produce a different state root; decoder
(if present) must reject malformed input.  Currently only serialization exists;
state is reconstructed via the deterministic reducer, not by decoding raw bytes.

### 3. Governance transactions

Path: `chainbreaker/governance.py`

Canonical form: JSON with sorted keys, `,`/`:` separators, no whitespace.

Attack vectors:

- Extra whitespace in JSON.
- Different key order.
- Different field names.
- Missing required fields.
- Unexpected fields.
- Hex case differences.
- Numeric string vs integer.

Expected behavior: transaction ID and signature domain must change when
encoding changes.  `HashEngine.hash_object` must be deterministic.

### 4. Attestation messages

Path: `chainbreaker/witness.py` (`attestation_message_v2`)

Canonical form: sorted JSON object.

Attack vectors:

- Different key order.
- Extra keys.
- Missing `block_height`.
- Wrong network_id.

Expected behavior: signature becomes invalid.

---

## Test plan

Add `tests/test_adversarial_serialization.py` containing:

1. Header canonical identity: `decode(encode(h)) == h`.
2. Header rejects extra trailing bytes.
3. Header rejects missing bytes.
4. Header rejects wrong type marker.
5. Header rejects swapped endianness.
6. Registry state root stability: same logical state always hashes to the same root.
7. Registry state order invariance: record order does not affect root (records are sorted).
8. Governance transaction canonical JSON: whitespace/ordering changes alter txid.
9. Attestation message canonical JSON: ordering/extra keys alter signature validity.
10. Negative/timestamp boundary tests.

---

## Success criteria

- Every target has deterministic, single canonical encoding.
- Fuzz-style mutation tests produce deterministic failures.
- No crash or uncontrolled exception on malformed input.
- All existing verification gates continue to pass.

---

## Findings to record

For each discovered issue:

- location
- severity
- exploit scenario
- consensus divergence risk
- fix
- regression test
