# Proof-of-Work v2 Specification

Version: `chainbreaker-scripture-v2`  
Status: **implemented and frozen at v2.0.0-alpha**

---

## 1. Purpose

This document defines the exact proof-of-work (PoW) rules for Protocol v2.

Consensus rule:

```text
A v2 block header is valid PoW if and only if:

    integer(double_sha256(canonical_header_bytes)) <= target
```

All fields are interpreted as fixed-size, big-endian, raw bytes.

---

## 2. Header canonicalization for PoW

The PoW check operates on the exact 149-byte v2 header serialization described
in `docs/HEADER_V2_DESIGN.md`:

| Offset | Size | Field           |
| -----: | ---: | --------------- |
| 0      | 1    | type marker     |
| 1      | 4    | version         |
| 5      | 32   | previous hash   |
| 37     | 32   | merkle root     |
| 69     | 32   | registry root   |
| 101    | 8    | timestamp       |
| 109    | 32   | target          |
| 141    | 8    | nonce           |

Encoding rules:

* `type marker`: single byte `0x02`.
* `version`: unsigned 32-bit little-endian integer, value `2`.
* `previous hash`, `merkle root`, `registry root`: 32 raw bytes.
* `timestamp`: unsigned 64-bit little-endian integer (seconds since Unix epoch).
* `target`: 32 raw bytes, big-endian unsigned integer interpretation.
* `nonce`: unsigned 64-bit little-endian integer.

The double-SHA256 hash is the 32-byte digest of `SHA256(SHA256(header))`.

The digest is interpreted as a **big-endian** unsigned 256-bit integer when
compared to the target.

---

## 3. Target representation

### 3.1 Integer range

The target is a 256-bit unsigned integer:

```text
MIN_TARGET = 1
MAX_TARGET = 0x0000FFFF00000000000000000000000000000000000000000000000000000000
```

`MAX_TARGET` is the easiest possible target (most leading zero bits in the
PoW hash). `MIN_TARGET` is the hardest possible target.

### 3.2 Byte encoding

The target is encoded as a 32-byte big-endian byte sequence. The canonical
hex string is therefore the left-padded big-endian representation.

Examples:

```text
MAX_TARGET integer -> bytes -> hex:
0000ffff00000000000000000000000000000000000000000000000000000000

MIN_TARGET integer -> bytes -> hex:
0000000000000000000000000000000000000000000000000000000000000001
```

The inverse conversion:

```text
hex_to_target(hex): int.from_bytes(bytes.fromhex(hex), "big")
target_to_hex(int):  int.to_bytes(32, "big").hex()
```

### 3.3 Comparison method

Given:

```text
H = double_sha256(header_bytes)       # 32 bytes
T = target                            # 32 bytes
```

PoW is valid when:

```text
int.from_bytes(H, "big") <= int.from_bytes(T, "big")
```

Equivalently, using hex strings:

```text
block_hash_hex <= target_hex
```

where both are 64-character hex strings compared lexicographically.

A block hash of `0000...0000` is always valid; a hash of `ffff...ffff` is
never valid except against `MAX_TARGET`.

---

## 4. Difficulty and chain work

### 4.1 Work per block

The work contributed by a single block is defined as:

```text
work = floor(MAX_TARGET / target)
```

For `target = MAX_TARGET`, work is `1`. For smaller targets, work increases.

### 4.2 Total chain work

The total chain work of a chain is the sum of per-block work:

```text
chain_work = sum(work_i) for all blocks i in the chain
```

The fork-choice rule:

```text
When comparing two valid chains, choose the chain with greater chain_work.
If chain_work is equal, choose the chain whose tip hash is lexicographically
smaller (deterministic tie-breaker).
```

### 4.3 Genesis work

Genesis uses `target = MAX_TARGET`, so:

```text
genesis_work = floor(MAX_TARGET / MAX_TARGET) = 1
```

This value is included in every chain's total work.

---

## 5. Difficulty retargeting

Retargeting occurs every `DIFFICULTY_RETARGET_INTERVAL = 10` blocks,
measured at height `h` where `h % 10 == 0` and `h > 0`.

The retarget formula:

```text
window_start_block = chain[h - 10]
window_end_block   = chain[h - 1]
actual_time        = max(1, window_end.timestamp - window_start.timestamp)
expected_time        = TARGET_BLOCK_TIME * 10
expected_time          = 600 * 10 = 6000 seconds

new_target = (old_target * actual_time) // expected_time
new_target = clamp(MIN_TARGET, new_target, MAX_TARGET)
new_target = clamp(old_target // 4, new_target, old_target * 4)
```

`old_target` is the target of the block immediately before the retarget
boundary (`chain[h - 1].header.target`).

Retargeting is deterministic and depends only on timestamps in the chain.

---

## 6. Genesis mining model

Genesis v2 is **pre-mined offline and hard-coded**.

The protocol constants are:

```text
GENESIS_TIMESTAMP = 1704067200
GENESIS_TARGET    = MAX_TARGET
GENESIS_NONCE     = 42129
GENESIS_HASH      = 0000a6fd1e57aafd19da552440faa94803dbf1a1773bcd9af8ce3e0ae9fd13db
GENESIS_HEADER_BYTES = <149 bytes>
```

A node does not mine genesis at runtime. It verifies the hard-coded bytes:

```text
verify_genesis():
    decode GENESIS_HEADER_BYTES
    check version == 2
    check network_id constant == "chainbreaker-scripture-v2"
    check target == GENESIS_TARGET_HEX
    check timestamp == GENESIS_TIMESTAMP
    check registry_root == GENESIS_REGISTRY_ROOT
    check double_sha256(GENESIS_HEADER_BYTES) == GENESIS_HASH
    check int(GENESIS_HASH, 16) <= GENESIS_TARGET
```

Generator tooling may recompute these constants for a new network, but the
production protocol treats them as immutable anchors.

---

## 7. Mining algorithm for non-genesis blocks

A miner constructs a candidate block:

```text
header = {
    version:       2,
    prev_hash:     parent.hash,
    merkle_root:   merkle_root(transactions),
    registry_root: registry_root_before_this_block,
    timestamp:     chosen timestamp,
    target:        expected_target_at(height),
    nonce:         0,
}
```

The miner repeatedly increments `nonce` and recomputes:

```text
serialized = encode_header_v2(header)
block_hash = double_sha256(serialized)
```

until:

```text
int(block_hash, 16) <= target
```

Only `nonce` may vary during the search. Changing any other field requires
restarting the search.

---

## 8. Mining test vectors

All vectors use big-endian target and hash interpretation.

### 8.1 Valid PoW vector

Header bytes (hex, truncated):

```text
020200000000...00000000ffff000000...0091a4000000000000
```

Target:

```text
0000ffff00000000000000000000000000000000000000000000000000000000
```

Nonce:

```text
42129
```

Hash:

```text
0000a6fd1e57aafd19da552440faa94803dbf1a1773bcd9af8ce3e0ae9fd13db
```

Result:

```text
valid
```

### 8.2 Invalid PoW vector (target = MAX_TARGET, nonce = 0)

Header bytes:

```text
0202000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000005814321ad489e630fef0350b1bff591d5cee8a821c00fa40a2cb2c99bd5b318680009265000000000000ffff000000000000000000000000000000000000000000000000000000000000000000000000
```

Hash:

```text
7e66292c39792eb892a6a1ae677f9794f0c12319381dd589c3fe17eb565816e0
```

Comparison:

```text
7e66... > 0000ffff...  ->  invalid
```

### 8.3 Target boundary vectors

A target of `0` is invalid (below `MIN_TARGET`).

A target of `MAX_TARGET` accepts approximately the easiest valid hash.

A target of `MIN_TARGET` only accepts the all-zero hash.

---

## 9. Compatibility behavior

v1 and v2 nodes use different header layouts and different network IDs. A v2
node must reject v1 blocks, and a v1 node must reject v2 blocks.

v2 nodes must not attempt to evaluate PoW on v1 headers.

---

## 10. Security notes

* Timestamp must not be part of the hash preimage in any other form; the
  canonical 8-byte little-endian timestamp is the only representation used.
* Nonce overflow is allowed; it wraps modulo 2^64.
* A miner must not reuse the same `registry_root` for two different blocks
  unless the blocks produce identical registry state transitions.
* Changing any header field other than `nonce` during mining invalidates the
  current search and requires recomputing `merkle_root` and `registry_root`.

---

## 11. References

* `docs/HEADER_V2_DESIGN.md` — header layout
* `docs/CONSENSUS_INVARIANTS.md` — consensus invariants
* `docs/GENESIS_V2_SPECIFICATION.md` — genesis constants
