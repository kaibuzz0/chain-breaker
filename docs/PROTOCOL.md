# Chain-Breaker Protocol Specification

Version: `chainbreaker-scripture-v1`

This document defines the exact rules for transaction encoding, block hashing,
target calculation, retargeting, chain work, genesis, witnesses, and registry
state. Any implementation must produce identical results for the same inputs.

## 1. Cryptographic primitives

- SHA-256 as defined by FIPS 180-4.
- Double-SHA-256: `SHA256(SHA256(x))`.
- Merkle tree: binary, bottom-up, double-SHA-256 of `left || right`. If a level
  has an odd number of nodes, the last node is duplicated.
- Ed25519 signatures as implemented by `cryptography` (RFC 8032).

All hash outputs are 32 bytes. All hex strings are lowercase.

## 2. Canonical JSON

Consensus objects may be serialized to canonical JSON for hashing with these
rules:

- `sort_keys=True`
- separators: `(",", ":")`
- encoding: UTF-8
- no whitespace
- keys and string values are strict UTF-8
- integers are decimal, no leading zeros, signed values are prefixed with `-`
- floating-point values, `NaN`, `Infinity`, and `-Infinity` are **not allowed**
- `None` / `null` is not allowed unless explicitly permitted by a schema
- maximum nesting depth: 32
- maximum string length: 65535 bytes
- maximum list/dict size: 10000 elements

For block headers and transactions, the canonical binary encoding (see below)
is authoritative. JSON is used only for human-readable display and for manifest
files that are not directly hashed by consensus.

## 3. Block header

A block header is a 6-tuple:

- `version` — unsigned 32-bit little-endian integer, currently `1`
- `prev_hash` — 32-byte hash of the previous block header
- `merkle_root` — 32-byte Merkle root of the block's transactions
- `timestamp` — unsigned 64-bit little-endian Unix seconds
- `target` — 32-byte unsigned integer in little-endian (proof-of-work target)
- `nonce` — unsigned 64-bit little-endian integer

The canonical serialized header is the concatenation of these fields, in order,
in little-endian byte order for multi-byte integers.

### 3.1 Header hash

`block_hash = SHA256(SHA256(header_bytes))`.

The hash is a 32-byte value, displayed as a 64-character lowercase hex string.

### 3.2 Proof of work

A header satisfies proof of work when:

```
int(block_hash, 16) <= int(target_bytes, 256)
```

The `target` field is encoded as a 32-byte unsigned integer in little-endian.
The maximum target is:

```
MAX_TARGET = 0x0000FFFF00000000000000000000000000000000000000000000000000000000
```

The minimum target is:

```
MIN_TARGET = 0x0000000000000000000000000000000000000000000000000000000000000001
```

Target validation rejects values outside `[MIN_TARGET, MAX_TARGET]`.

### 3.3 Difficulty

For human display only, difficulty is defined as:

```
difficulty = MAX_TARGET / target
```

Consensus does not use difficulty directly; it uses the 256-bit target.

## 4. Difficulty retargeting

Retargeting occurs every `RETARGET_INTERVAL = 10` blocks, starting at height
10, 20, 30, etc. The first retarget at height 10 uses blocks 1 through 10.

For a retarget at height `H`:

```
first_block = chain[H - RETARGET_INTERVAL]
last_block = chain[H - 1]
actual_time = last_block.timestamp - first_block.timestamp
expected_time = TARGET_BLOCK_TIME * RETARGET_INTERVAL
TARGET_BLOCK_TIME = 600 seconds
```

If `actual_time <= 0`, set `actual_time = 1`.

The new target is:

```
new_target = old_target * actual_time / expected_time
```

Then clamp:

```
new_target = max(MIN_TARGET, min(MAX_TARGET, new_target))
```

The target change between two retargets is also limited to a factor of 4:

```
if new_target < old_target / 4: new_target = old_target / 4
if new_target > old_target * 4: new_target = old_target * 4
```

Retargeting is deterministic: all nodes with the same chain compute the same
new target.

## 5. Genesis block

The genesis block is hard-coded. Its fields are:

- `version`: 1
- `prev_hash`: 32 zero bytes
- `merkle_root`: the Merkle root of `[genesis_transaction]`
- `timestamp`: 1704067200 (2024-01-01 00:00:00 UTC)
- `target`: `0x0000000000000000FFFF00000000000000000000000000000000000000000000`
- `nonce`: hard-coded after mining the genesis once

The genesis transaction is:

```json
{
  "version": 1,
  "type": "genesis",
  "body": {
    "network_id": "chainbreaker-scripture-v1",
    "message": "Chain-Breaker Genesis: scripture preservation ledger",
    "timestamp": 1704067200
  },
  "witnesses": []
}
```

## 6. Transactions

A transaction is a dictionary with these exact top-level keys:

- `version` — integer, currently `1`
- `type` — string, one of: `"genesis"`, `"scripture"`, `"registry"`
- `body` — dict, schema depends on `type`
- `witnesses` — list of witness dicts

### 6.1 Scripture / archive transaction body

```json
{
  "schema": "chainbreaker-manifest-v1",
  "content_hash": "64-char hex SHA-256",
  "byte_length": integer,
  "media_type": string,
  "title": string,
  "language": string or null,
  "source": string or null,
  "source_uri": string or null,
  "acquisition_date": integer (Unix seconds) or null,
  "license": string or null,
  "parent_hash": 64-char hex or null,
  "metadata_hash": 64-char hex,
  "notes_hash": 64-char hex or null
}
```

All hashes must be 64 lowercase hex characters. `byte_length` must be positive.
No field may contain floats, NaN, or Infinity.

### 6.2 Registry transaction body

```json
{
  "action": "add" | "revoke" | "rotate",
  "curator_id": string,
  "public_key_hex": "64-char hex Ed25519 public key",
  "activation_height": integer,
  "revocation_height": integer or null,
  "previous_key_hex": "64-char hex or null"
}
```

Registry transactions must be attested by a network-governance key (not yet
implemented in this release).

## 7. Witnesses

A witness is:

```json
{
  "curator_id": string,
  "timestamp": integer (Unix seconds),
  "signature": "128-char hex Ed25519 signature"
}
```

The curator signs the canonical attestation message:

```json
{
  "network_id": "chainbreaker-scripture-v1",
  "version": 1,
  "body_hash": "64-char hex SHA-256 of the transaction body",
  "curator_id": "the curator's ID",
  "timestamp": integer
}
```

The signature is Ed25519 over the SHA-256 hash of the canonical JSON of the
above message.

### 7.1 Freshness vs. historical validity

- When a transaction is first submitted, a node may require the witness timestamp
  to be within a recent window (e.g., 24 hours).
- Once a transaction is included in an accepted block, its witnesses are
  permanently valid. Historical chain validation must not reject old
  attestations because time has passed.

### 7.2 Required attestations

A `"scripture"` transaction must carry at least one valid witness from a
registered, active curator. A block containing a scripture transaction without
sufficient valid witnesses is invalid.

Duplicate curator IDs in the witness list make the transaction invalid.

## 8. Block validation

A block is valid if and only if:

1. The header fields deserialize correctly.
2. The recomputed header hash satisfies proof of work against the header target.
3. The Merkle root matches the transactions.
4. The timestamp is:
   - greater than the median of the previous 11 block timestamps (or fewer at
     the start of the chain), and
   - not more than 2 hours in the future.
5. The target equals the expected target at this height.
6. `prev_hash` equals the recomputed hash of the previous block.
7. Every transaction is valid according to its type and required witnesses.
8. Genesis block matches the hard-coded constants.

## 9. Chain work

The work of a block is:

```
work = (2**256 - target) / (target + 1)
```

Chain work is the sum of work for all blocks. Fork choice selects the chain with
the most accumulated work.

## 10. Canonical binary encoding

The binary encoding is used for network messages and deterministic hashing.
All integers use explicit little-endian byte order.

### 10.1 Block header

| Field | Size | Encoding |
|-------|------|----------|
| type marker | 1 byte | 0x02 |
| version | 4 bytes | uint32 LE |
| prev_hash | 32 bytes | hash |
| merkle_root | 32 bytes | hash |
| timestamp | 8 bytes | uint64 LE |
| target | 32 bytes | uint256 LE |
| nonce | 8 bytes | uint64 LE |

### 10.2 Transaction

| Field | Size | Encoding |
|-------|------|----------|
| type marker | 1 byte | 0x01 |
| version | varint | compact |
| tx_type | varint + bytes | strict UTF-8 string |
| body | varint + bytes | canonical JSON bytes |
| witnesses | varint + bytes | canonical JSON bytes |

All decoding operations check bounds before slicing. Malformed input raises a
controlled `CodecError`.

## 11. Registry state

Curator state is committed to the ledger through `"registry"` transactions.
A curator entry contains:

- `curator_id` — unique string
- `public_key_hex` — 64-char hex Ed25519 public key
- `activation_height` — first block height at which attestations are valid
- `revocation_height` — first block height at which attestations are no longer
  valid, or null for active curators

A curator's key must be unique within the active period. Two curators may not
share the same public key at the same height.

## 12. Unresolved / deferred items

- Network P2P protocol
- Private encrypted vault
- Currency / tokenomics
- Cross-language canonical format beyond Python JSON
- Hardware-wallet or HSM key management
- Formal security audit
