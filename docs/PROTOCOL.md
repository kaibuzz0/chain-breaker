# Chain-Breaker Protocol Specification

Version: `chainbreaker-scripture-v2`

Status: **alpha prototype, not production-ready**

This document is the canonical source of truth for the Chain-Breaker
scripture-preservation ledger. Every consensus rule, binary encoding,
transaction schema, hash algorithm, difficulty calculation, and governance
mechanism is defined here. Future implementations in any language must
reproduce the exact same deterministic results for the same inputs.

## 1. Versioning and compatibility

- Protocol version: `2`
- Network ID: `chainbreaker-scripture-v2`
- Package version: `0.3.0`
- This release is **not backward compatible** with `chainbreaker-scripture-v1`.
  The block header format gained a `registry_root` field, which changes the
  canonical header bytes and therefore all block hashes. Old testnet data
  must be reset.

## 2. Cryptographic primitives

- SHA-256 as defined by FIPS 180-4.
- Double-SHA-256: `SHA256(SHA256(x))`.
- Merkle tree: binary, bottom-up, double-SHA-256 of `left || right`. If a level
  has an odd number of nodes, the last node is duplicated.
- Ed25519 signatures as specified by RFC 8032.

All hash outputs are 32 bytes. All hex strings are lowercase.

### 2.1 Key formats

- Ed25519 public keys: 32 raw bytes, displayed as 64 lowercase hex characters.
- Ed25519 private keys: 32 raw bytes, displayed as 64 lowercase hex characters.
- Ed25519 signatures: 64 raw bytes, displayed as 128 lowercase hex characters.

## 3. Canonical JSON

Consensus objects may be serialized to canonical JSON for hashing with these
rules:

- `sort_keys=True`
- separators: `(",", ":")`
- encoding: UTF-8
- no whitespace
- keys and string values are strict UTF-8
- integers are decimal, no leading zeros, signed values are prefixed with `-`
- floating-point values, `NaN`, `Infinity`, and `-Infinity` are **not allowed**
- `None` / `null` is allowed only where a schema explicitly permits it
- maximum nesting depth: 32
- maximum string length: 65535 bytes
- maximum list/dict size: 10000 elements

For block headers and transactions, the canonical binary encoding (Section 10)
is authoritative. JSON is used only for human-readable display and for object
schemas that are not directly hashed by consensus.

## 4. Network identifier

The network ID is a domain separator. It appears in:

- genesis transaction body
- attestation messages
- governance messages
- registry-state commitments

Network ID: `chainbreaker-scripture-v2`

A valid node must reject any transaction, block, attestation, or governance
message whose network ID does not exactly match its configured network ID.

## 5. Block header

A block header is a 7-tuple:

| Field | Size | Encoding |
|-------|------|----------|
| version | 4 bytes | uint32 little-endian |
| prev_hash | 32 bytes | SHA-256 header hash of previous block |
| merkle_root | 32 bytes | Merkle root of this block's transactions |
| registry_root | 32 bytes | SHA-256 of canonical active registry state |
| timestamp | 8 bytes | uint64 little-endian Unix seconds |
| target | 32 bytes | uint256 little-endian proof-of-work target |
| nonce | 8 bytes | uint64 little-endian |

The canonical serialized header is the concatenation of these fields in the
table order, using little-endian byte order for all multi-byte integers.

### 5.1 Header hash

`header_hash = SHA256(SHA256(header_bytes))`

The hash is a 32-byte value, displayed as a 64-character lowercase hex string.

### 5.2 Proof of work

A header satisfies proof of work when:

```
int(header_hash, 16) <= target
```

The comparison treats the 32-byte hash and the 32-byte target as unsigned
256-bit integers. The hash is interpreted in big-endian byte order (the natural
hex digit order). The target is the value of the 32 little-endian bytes.

### 5.3 Target bounds

```
MAX_TARGET = 0x0000FFFF00000000000000000000000000000000000000000000000000000000
MIN_TARGET = 0x0000000000000000000000000000000000000000000000000000000000000001
```

A target is valid only if `MIN_TARGET <= target <= MAX_TARGET`.

### 5.4 Difficulty (display only)

For human display:

```
difficulty = MAX_TARGET / target
```

Consensus never uses difficulty directly.

### 5.5 Registry root

`registry_root` in block `N` is the SHA-256 hash of the canonical serialized
registry state (Section 10.3) **after replaying blocks 0 through N-1**. In
other words, the root is the state that exists *before* the transactions in
block `N` are applied.

- Block 0 (genesis): `registry_root` is the hash of the empty registry state.
- Block 1: `registry_root` is the hash of the state after applying genesis.
- Block N: `registry_root` is the hash of the state after applying blocks 0..N-1.

The transactions in block `N` may produce a new registry state; that new
state becomes the `registry_root` in block `N+1`.

Every block must carry the correct registry root for its height. Historical
validation recomputes every registry root from genesis.

## 6. Difficulty retargeting

Retargeting occurs every `RETARGET_INTERVAL = 10` blocks, at heights that are
multiples of 10: 10, 20, 30, ...

For a retarget at height `H`:

```
first_block = chain[H - RETARGET_INTERVAL]
last_block = chain[H - 1]
actual_time = last_block.timestamp - first_block.timestamp
expected_time = TARGET_BLOCK_TIME * RETARGET_INTERVAL
TARGET_BLOCK_TIME = 600 seconds
```

If `actual_time <= 0`, set `actual_time = 1`.

```
new_target = old_target * actual_time / expected_time
```

Then clamp to absolute bounds:

```
new_target = max(MIN_TARGET, min(MAX_TARGET, new_target))
```

Then clamp to per-retarget factor-of-4 limits:

```
min_allowed = old_target // 4
max_allowed = old_target * 4
new_target = max(min_allowed, min(max_allowed, new_target))
```

Retargeting is deterministic: all nodes with the same chain compute the same
new target. Integer division is used for the factor-of-4 clamp.

For non-retarget heights, the target is the same as the previous block's
target.

## 7. Genesis block

The genesis block is hard-coded. Its fields are:

| Field | Value |
|-------|-------|
| version | 2 |
| prev_hash | 32 zero bytes |
| merkle_root | Merkle root of `[genesis_transaction]` |
| registry_root | hash of empty registry state |
| timestamp | 1704067200 (2024-01-01 00:00:00 UTC) |
| target | MAX_TARGET |
| nonce | to be determined by mining once and then hard-coded |

The genesis transaction body is:

```json
{
  "network_id": "chainbreaker-scripture-v2",
  "message": "Chain-Breaker Genesis: scripture preservation ledger",
  "timestamp": 1704067200,
  "governance_keys": [
    "<64-hex Ed25519 public key>",
    "<64-hex Ed25519 public key>",
    "<64-hex Ed25519 public key>"
  ],
  "governance_threshold": 2
}
```

The exact governance keys and threshold are chosen by the network launcher and
committed once at genesis. They cannot be changed without a new network.

## 8. Chain work

The work of a block with target `T` is:

```
work = (2**256 - T) // (T + 1)
```

Chain work is the integer sum of work for all blocks. Fork choice selects the
chain with the greatest accumulated chain work. Ties are broken by the chain
whose tip has the lexicographically smaller header hash.

## 9. Transactions

A transaction is a dictionary with these exact top-level keys:

- `version` — integer, currently `2`
- `type` — string, one of: `"genesis"`, `"scripture"`, `"registry"`
- `body` — dict, schema depends on `type`
- `witnesses` — list of witness dicts

A transaction is invalid if it has extra top-level keys, missing top-level
keys, or an unsupported type.

The **transaction ID** of a transaction is `SHA256(SHA256(canonical_transaction_bytes))`,
where `canonical_transaction_bytes` is the binary encoding defined in
Section 12.5. The transaction ID is used for replay prevention and for
referencing the governance transaction that created, rotated, or revoked a
curator entry.

### 9.1 Genesis transaction

`type`: `"genesis"`

Body schema (Section 7):

- `network_id`: string, must equal network ID
- `message`: string, maximum 65535 bytes
- `timestamp`: integer, must equal genesis timestamp
- `governance_keys`: list of 1 to 16 distinct 64-hex Ed25519 public keys
- `governance_threshold`: integer, `1 <= threshold <= len(governance_keys)`

### 9.2 Scripture / archive transaction

`type`: `"scripture"`

Body schema:

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
  "acquisition_date": integer or null,
  "license": string or null,
  "parent_hash": "64-char hex or null",
  "metadata_hash": "64-char hex",
  "notes_hash": "64-char hex or null"
}
```

Validation rules:

- `byte_length` must be a positive integer.
- All non-null hash fields must be 64 lowercase hex characters.
- No field may contain floats, NaN, Infinity, or unsupported types.
- Required keys must be present exactly.
- No extra keys are allowed.

### 9.3 Registry governance transaction

`type`: `"registry"`

Body schema depends on `action`:

Common fields for all registry actions:

- `action`: one of `"curator_register"`, `"curator_rotate"`, `"curator_revoke"`
- `curator_id`: string, 1 to 128 UTF-8 bytes
- `public_key_hex`: 64-char hex Ed25519 public key
- `activation_height`: integer, `>= 0`
- `previous_registry_root`: 64-char hex SHA-256

#### 9.3.1 `curator_register`

Additional fields:

- `display_metadata_hash`: 64-char hex or null
- `governance_signatures`: list of governance signatures (Section 9.4)

Rules:

- `curator_id` must not already be registered (even if not yet active).
- `public_key_hex` must not already be registered under another curator ID
  (even if not yet active).
- `activation_height` must be strictly greater than the block height at which
  the registration transaction is included. The curator becomes active for
  blocks whose height is `>= activation_height`.
- The entry appears in the registry state immediately after the registration
  transaction is applied, but attestations are valid only at heights
  `>= activation_height`.

#### 9.3.2 `curator_rotate`

Additional fields:

- `new_public_key_hex`: 64-char hex Ed25519 public key
- `display_metadata_hash`: 64-char hex or null
- `governance_signatures`: list of governance signatures

Rules:

- `curator_id` must be active at the block height where the rotation
  transaction is included.
- The rotation body must be signed by the currently active curator private key
  and by the required number of genesis governance keys.
- The new `public_key_hex` becomes the active key at `activation_height`.
- The old key remains valid only for blocks with height strictly less than
  `activation_height`.
- The old key must be recorded as `previous_key_hex` of the new entry.
- The new key must not already be registered under another curator ID.

#### 9.3.3 `curator_revoke`

Additional fields:

- `revocation_height`: integer, `>= activation_height` of the active key
- `reason_code`: string, 1 to 64 UTF-8 bytes
- `governance_signatures`: list of governance signatures

Rules:

- `curator_id` must be active at the block height where the revocation
  transaction is included.
- The revocation body must be signed by the currently active curator private
  key and by the required number of genesis governance keys.
- `revocation_height` must be strictly greater than the current block height.
- The curator's active key becomes invalid for blocks whose height is
  `>= revocation_height`.
- A revoked curator ID cannot be re-registered; a revoked public key cannot
  be reused under a different curator ID.

### 9.4 Governance signatures

A governance signature is:

```json
{
  "key_index": integer,
  "signature": "128-char hex Ed25519 signature"
}
```

The signed message is the canonical JSON of:

```json
{
  "network_id": "chainbreaker-scripture-v2",
  "version": 2,
  "type": "registry",
  "body_hash": "64-char hex SHA-256 of transaction body"
}
```

Validation rules:

- `key_index` must reference a governance key defined in the genesis block.
- Duplicate `key_index` values in the same transaction are invalid.
- A signature from an unknown governance key is invalid.
- The number of valid signatures must be at least the genesis threshold.
- Signatures are checked against the transaction body hash, not the full
  transaction.

### 9.5 Witnesses

A curator witness is:

```json
{
  "curator_id": string,
  "timestamp": integer,
  "signature": "128-char hex Ed25519 signature"
}
```

The curator signs the canonical JSON of:

```json
{
  "network_id": "chainbreaker-scripture-v2",
  "version": 2,
  "body_hash": "64-char hex SHA-256 of transaction body",
  "curator_id": "the curator's ID",
  "timestamp": integer
}
```

Validation rules:

- `curator_id` must be a registered, active curator at the block height where
  the transaction is included.
- The signature must be valid under the active public key at that height.
- The same curator may appear only once in a transaction's witness list.
- A scripture transaction must have at least one valid witness.
- Freshness (timestamp recency) is a mempool/submission-time check only;
  historical validation never rejects old attestations.

## 10. Registry state

### 10.1 State representation

The registry state at a given height is the set of curator entries that are
registered. Each entry tracks when it is active. An entry is:

```
{
  curator_id: string,
  public_key_hex: string,
  activation_height: integer,
  revocation_height: integer or null,
  previous_key_hex: string or null,
  registration_txid: 64-char hex,
  latest_rotation_txid: 64-char hex or null
}
```

### 10.2 Deterministic reducer

Registry state is derived deterministically by replaying accepted registry
transactions in block order from genesis. The reducer:

- takes the previous state, a validated transaction body, and the current block
  height;
- returns either a new state or a controlled validation failure;
- never reads the filesystem, wall clock, random source, or network;
- never uses mutable global state.

### 10.3 Canonical active-state serialization

The active registry state for a block is the sorted list of all entries that are
active at that block's height. Sorting is by `curator_id` ascending in UTF-8
byte order.

The canonical serialization of one entry is the concatenation of:

- `version`: 4 bytes uint32 LE, value `2`
- `curator_id`: varint length + strict UTF-8 bytes
- `public_key_hex`: 32 raw bytes
- `activation_height`: 8 bytes uint64 LE
- `revocation_height`: 8 bytes uint64 LE, or `0xFFFFFFFFFFFFFFFF` for null
- `previous_key_hex`: 32 raw bytes, or 32 zero bytes for null

The canonical serialization of the registry state is the concatenation
of all entry serializations, preceded by:

- `state_version`: 4 bytes uint32 LE, value `2`
- `network_id`: varint length + strict UTF-8 bytes
- `entry_count`: varint

`registry_root = SHA256(canonical_registry_state_bytes)`.

The empty registry state serialization is `state_version=2`, the network ID
string, and `entry_count=0`. Its registry root is deterministic and can be used
as a fixed test vector.

### 10.4 State transition rules

All transitions are applied to the registry state that exists *after* all
previous blocks. The resulting state does **not** yet affect the current
block's `registry_root`; it affects the next block's `registry_root`.

- `curator_register`: adds a new entry with `revocation_height = null`,
  `previous_key_hex = null`, `registration_txid = txid`,
  `latest_rotation_txid = null`. Fails if `curator_id` or `public_key_hex` is
  already registered at any height (active, pending, or revoked).
- `curator_rotate`: sets the existing entry's `revocation_height` to the new
  key's `activation_height`, and adds a new entry with
  `previous_key_hex = old public_key_hex`, `registration_txid` copied from the
  old entry, and `latest_rotation_txid = txid`. Fails if the old key is not
  active at the current block height.
- `curator_revoke`: sets the existing entry's `revocation_height`. Fails if
  the entry is not active at the current block height. The `latest_rotation_txid`
  is updated to the revocation transaction ID.

## 11. Block validation

A block is valid if and only if:

1. The header fields deserialize correctly.
2. `target` is within `[MIN_TARGET, MAX_TARGET]`.
3. The recomputed header hash satisfies proof of work.
4. The Merkle root matches the transactions.
5. `registry_root` matches the active registry state at this height.
6. The timestamp is greater than the median of the previous 11 block timestamps.
7. The timestamp is not more than 2 hours in the future.
8. `target` equals the expected target at this height.
9. `prev_hash` equals the recomputed hash of the previous block.
10. Every transaction is valid according to its type and required witnesses or
    governance signatures.
11. The genesis block matches the hard-coded constants.

## 12. Canonical binary encoding

### 12.1 Varint

Same as Bitcoin-style compact unsigned integer:

- `n < 0xFD`: 1 byte, value
- `n <= 0xFFFF`: `0xFD` + 2 bytes uint16 LE
- `n <= 0xFFFFFFFF`: `0xFE` + 4 bytes uint32 LE
- `n <= 0xFFFFFFFFFFFFFFFF`: `0xFF` + 8 bytes uint64 LE

Decoder must reject non-canonical encodings (e.g., encoding a value that would
fit in a shorter form with a longer prefix).

### 12.2 Hash

32 raw bytes. Hex display is lowercase.

### 12.3 Address

Not used in this release.

### 12.4 Block header

| Field | Size | Encoding |
|-------|------|----------|
| type marker | 1 byte | `0x02` |
| version | 4 bytes | uint32 LE |
| prev_hash | 32 bytes | hash |
| merkle_root | 32 bytes | hash |
| registry_root | 32 bytes | hash |
| timestamp | 8 bytes | uint64 LE |
| target | 32 bytes | uint256 LE |
| nonce | 8 bytes | uint64 LE |

### 12.5 Transaction

| Field | Size | Encoding |
|-------|------|----------|
| type marker | 1 byte | `0x01` |
| version | varint | canonical |
| tx_type | varint + bytes | strict UTF-8 |
| body | varint + bytes | canonical JSON |
| witnesses | varint + bytes | canonical JSON |

All decoding operations check bounds before slicing. Malformed input raises a
controlled `CodecError`.

## 13. Fork and reorganization rules

Because there is no P2P layer in this release, fork handling is local-only:

- Each distinct chain branch has its own registry-state derivation.
- When a competing branch has more chain work, the node switches to it.
- The registry state of the abandoned branch is discarded.
- The registry state of the winning branch is rebuilt by replaying its blocks
  from genesis.
- No state from an abandoned branch may leak into the active chain.

## 14. Threat model and limitations

This release uses a fixed genesis governance key set. That is a centralized
alpha-stage mechanism, not decentralized governance. It is honest about that
limitation.

A node must not trust any locally configured curator list for consensus. The
only valid registry state is the one derived from the chain.

The network ID prevents cross-network replay.

There is no P2P network layer, no cryptocurrency, and no encrypted private vault
in this release.

## 15. Test vectors

To be generated after genesis governance keys and constants are finalized.

## 16. Migration and versioning rules

- Any change to header serialization, transaction schemas, genesis constants,
  the reducer, or hash algorithms requires a protocol-version bump.
- Nodes with different protocol versions cannot validate each other's chains.
- No automatic migration of incompatible consensus data is implemented.
