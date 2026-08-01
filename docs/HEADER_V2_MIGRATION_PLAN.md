# Header v2 Migration Plan

Version: `chainbreaker-scripture-v2`  
Status: **design-only; no implementation yet**

This document defines how to migrate the `chainbreaker` codebase from Protocol
v1 to Protocol v2 without introducing an unreviewed consensus rewrite.  It
also splits Milestone 4 into five smaller, independently verifiable
implementation milestones.

---

## 1. Migration principle

Protocol v2 is a **new network**, not an upgrade of v1.

V1 and v2 are incompatible because:

- header size changed (117 bytes → 149 bytes)
- header hash preimage changed (new `registry_root` field)
- genesis block changed
- network ID changed
- protocol version changed

Therefore:

```text
A v1 node must reject v2 blocks.
A v2 node must reject v1 blocks.
There is no in-protocol bridge.
```

This is a network reset, not a hard fork.  Existing v1 chains remain invalid
under v2 rules.

---

## 2. Old chain handling

### 2.1 V1 nodes encountering v2 data

A v1 node that receives a v2 header will:

1. Decode the first byte as the type marker (`0x01`).
2. Read the next 4 bytes as the version (`2`).
3. Because v1 expects `PROTOCOL_VERSION = 1`, the node rejects the block.

The rejection is deterministic and safe.

### 2.2 V2 nodes encountering v1 data

A v2 node that receives a v1 header will:

1. Decode the first byte as the type marker (`0x01`).
2. Read the next 4 bytes as the version (`1`).
3. Because v2 expects `PROTOCOL_VERSION = 2`, the node rejects the block.

The rejection is deterministic and safe.

### 2.3 No migration tool provided

There is no tool to convert a v1 chain into a v2 chain.  The reasons:

- v1 blocks do not contain `registry_root`.
- v1 blocks do not contain curator governance transactions.
- Reconstructing a v2 registry state from v1 data would require arbitrary
  policy decisions about which attestations are legitimate.
- The protocol version change is intentionally clean break.

A fresh v2 genesis is required.

### 2.4 Data preservation outside consensus

Document attestations and file metadata stored outside the chain (e.g. in a
local archive or separate storage layer) can be re-anchored to the v2 chain by
issuing new witness transactions.  This is an application-layer operation, not
a consensus migration.

---

## 3. Byte-level header v2 table

The v2 header is a fixed-layout, 149-byte structure.  Offsets are inclusive
start positions.

| Field          | Type      | Size | Start | End  | Notes |
|----------------|-----------|------|-------|------|-------|
| type marker    | uint8     | 1    | 0     | 1    | `0x01` (`BinaryCodec.TYPE_HEADER`) |
| version        | uint32 LE | 4    | 1     | 5    | protocol version = `2` |
| prev_hash      | bytes     | 32   | 5     | 37   | SHA-256 of previous header, raw 32 bytes |
| merkle_root    | bytes     | 32   | 37    | 69   | transaction Merkle root, raw 32 bytes |
| registry_root  | bytes     | 32   | 69    | 101  | registry-state commitment, raw 32 bytes |
| timestamp      | uint64 LE | 8    | 101   | 109  | Unix seconds since epoch |
| target         | bytes     | 32   | 109   | 141  | 256-bit difficulty target, raw 32 bytes |
| nonce          | uint64 LE | 8    | 141   | 149  | proof-of-work nonce |

**Total size: 149 bytes.**

All multi-byte integers are **little-endian**.  All hash fields are raw bytes,
not hex strings.  No padding or alignment is added.

### Hash preimage

The block hash is:

```text
SHA-256(SHA-256(bytes[0:149]))
```

Any change to any byte in the header, including `registry_root`, changes the
block hash.

### Validation rules

- The type marker must equal `0x01`.
- The version must equal `2`.
- `prev_hash` must be exactly 32 bytes.
- `merkle_root` must be exactly 32 bytes.
- `registry_root` must be exactly 32 bytes.
- `timestamp` must be a non-negative integer.
- `target` must represent an integer in `[MIN_TARGET, MAX_TARGET]`.
- `nonce` may be any 64-bit unsigned integer.

---

## 4. New and changed constants

| Constant | V1 value | V2 value | Reason |
|----------|----------|------------|--------|
| `PROTOCOL_VERSION` | `1` | `2` | header format changed |
| `NETWORK_ID` | `chainbreaker-scripture-v1` | `chainbreaker-scripture-v2` | network isolation |
| `GENESIS_MESSAGE` | v1 message | new v2 message | fresh network identity |
| `GENESIS_TIMESTAMP` | `1704067200` | `1704067200` or new epoch | documented per network |
| `GENESIS_TARGET` | `MAX_TARGET` | `MAX_TARGET` | unchanged |
| `GENESIS_MERKLE_ROOT` | `"0" * 64` | `"0" * 64` | genesis has no transactions |
| `GENESIS_REGISTRY_ROOT` | not present | `registry_root(genesis_state)` | new field |
| package version | `0.2.0` | `0.3.0` | protocol break |

The genesis governance keys and threshold are protocol constants defined in:

```text
genesis configuration document
GENESIS_GOVERNANCE_KEYS
GENESIS_THRESHOLD
```

They are not computed at runtime.

---

## 5. Files touched by migration

| File | V1 role | V2 change |
|------|---------|-----------|
| `chainbreaker/block.py` | block header and PoW | add `registry_root`; bump constants; recompute genesis |
| `chainbreaker/codec.py` | binary serialization | add v2 header encode/decode; keep v1 decoder for rejection tests |
| `chainbreaker/chain.py` | chain state | ledger-derived registry state; validate header roots; fork handling |
| `chainbreaker/witness.py` | attestation validation | validate against historical registry state |
| `chainbreaker/cli.py` | mining CLI | use real curator identity; reject placeholder signers |
| `chainbreaker/governance.py` | new module | unchanged API; used by chain admission |
| `chainbreaker/registry_state.py` | new module | add `RegistryState.genesis()` factory |
| `pyproject.toml` | package metadata | bump version to `0.3.0` |
| `requirements.txt` | dependencies | unchanged |
| `docs/PROTOCOL.md` | protocol spec | update with final genesis values |
| `docs/HEADER_V2_TEST_VECTORS.md` | vectors | fill in computed genesis and header hashes |
| `tests/` | test suite | add v2 vectors; update legacy tests |

---

## 6. Milestone 4 split

Milestone 4 is the dangerous consensus integration.  It is split into five
sub-milestones.  Each sub-milestone must pass the full verification suite
before the next begins.

### 6A — Header data structures only

Scope:

- Update `chainbreaker/block.py` with v2 `BlockHeader` dataclass.
- Update `chainbreaker/codec.py` with v2 `encode_header` / `decode_header`.
- Add v2 header round-trip tests.
- Verify old v1 headers decode to the same dictionary shape where possible,
  or are rejected with a clear `CodecError`.

Forbidden in 4A:

- mining
- genesis recomputation
- chain validation
- registry integration

Commit message: `implement header v2 data structures`

---

### 6B — Genesis v2

Scope:

- Implement `RegistryState.genesis(governance_keys, threshold)` in
  `chainbreaker/registry_state.py`.
- Define `GENESIS_GOVERNANCE_KEYS` and `GENESIS_THRESHOLD` in
  `chainbreaker/block.py` as protocol constants.
- Recompute `GENESIS_NONCE`, `GENESIS_HASH`, and `GENESIS_REGISTRY_ROOT`.
- Add genesis tests verifying the v2 genesis block satisfies target and has
  the correct registry root.

Forbidden in 6B:

- chain validation beyond genesis
- mining of non-genesis blocks
- witness historical validation

Commit message: `implement genesis v2 and registry genesis state`

---

### 6C — Mining and PoW integration

Scope:

- Update CLI mining to produce v2 headers.
- Recompute target validation for v2 headers.
- Update block hashing in `block.py` to use the 149-byte v2 preimage.
- Add mining tests with known nonce solutions.

Forbidden in 6C:

- curator attestation validation
- governance transaction admission
- chain replay

Commit message: `integrate proof of work with v2 header`

---

### 6D — Ledger registry-root validation

Scope:

- In `chainbreaker/chain.py`, maintain per-chain-branch registry state.
- On `add_block`, validate `header.registry_root` against replayed state.
- Apply governance transactions to derive the post-block registry state.
- Handle reorgs by replaying the new active branch.
- Add fork/reorg tests with registry state divergence.

Forbidden in 6D:

- witness historical attestation validation (this milestone focuses on registry
  state, not attestation signatures)

Commit message: `integrate ledger-derived registry root validation`

---

### 6E — Historical attestation validation

Scope:

- In `chainbreaker/witness.py`, validate attestations against
  `curator_key_at(state_at_height, curator_id, height)`.
- Reject attestations signed by revoked or not-yet-active keys.
- Update CLI mining to require valid attestations.
- Add historical attestation boundary tests.

Commit message: `implement historical attestation validation`

---

## 7. Cross-milestone rules

1. **No milestone may introduce a consensus regression.**  If a sub-milestone
   breaks existing tests, it must be fixed before proceeding.

2. **Each milestone must update `docs/HEADER_V2_TEST_VECTORS.md` with any new
   fixed vectors it produces.**  Vectors are immutable once published.

3. **Each milestone must run the full verification suite:**
   - `python -m pytest -v`
   - `python -m pytest --cov=chainbreaker --cov-report=term-missing`
   - `python -m ruff check chainbreaker tests`
   - `python -m mypy chainbreaker`
   - `python -m build`
   - `python -m pip_audit -r requirements.txt`
   - `python -m bandit -r chainbreaker`

4. **No PR is opened until all five sub-milestones are complete and verified.**

5. **P2P networking remains forbidden** throughout Milestone 4.

6. **Cryptocurrency, tokenomics, wallets, and encrypted vaults remain
   forbidden** throughout Milestone 4.

---

## 8. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Header offset bug | Use the byte table; add decode/encode round-trip tests; assert exact byte length |
| Genesis constants wrong | Recompute in two fresh processes; verify genesis hash satisfies target |
| Old tests break | Update them with v2 vectors; do not keep stale v1 expectations |
| Registry state diverges on reorg | Replay the new branch from the fork point; never cache state globally |
| Historical attestation uses current key | Always query `curator_key_at(state, id, height)` |
| Placeholder signer returns | Remove placeholder paths from CLI and add failing tests for unsigned blocks |

---

## 9. Definition of done for Milestone 4

Milestone 4 is complete when:

- All five sub-milestones are committed.
- The full verification suite passes on the final commit.
- `docs/HEADER_V2_TEST_VECTORS.md` contains exact vectors for:
  - empty registry root
  - genesis registry root
  - genesis header bytes and hash
  - sample v2 block header bytes and hash
  - one valid register/rotate/revoke cycle
- No v1 code remains in the hot consensus path.
- A new PR can be opened.
