# Header v2 Design: Registry Root Integration

Version: `chainbreaker-scripture-v2`  
Status: **design-only milestone; no implementation yet**

This document specifies how the `registry_root` commitment is added to block
headers.  It is the canonical design that the next implementation milestone
must follow.

---

## Decision summary

`registry_root` is placed inside the block header, between `merkle_root` and
`timestamp`.

A system-transaction alternative was rejected because it creates ordering,
Merkle-inclusion, and replay questions that the header field solves directly.

---

## Header v2 layout

| Offset | Field | Type | Size | Notes |
|--------|-------|------|------|-------|
| 0 | type marker | uint8 | 1 | `0x02` (BinaryCodec.TYPE_HEADER) |
| 1 | version | uint32 LE | 4 | protocol version = `2` |
| 5 | prev_hash | bytes | 32 | SHA-256 hex string, 32 raw bytes |
| 37 | merkle_root | bytes | 32 | transaction Merkle root, 32 raw bytes |
| 69 | registry_root | bytes | 32 | registry-state commitment, 32 raw bytes |
| 101 | timestamp | uint64 LE | 8 | Unix seconds |
| 109 | target | bytes | 32 | 256-bit difficulty target, 32 raw bytes |
| 141 | nonce | uint64 LE | 8 | proof-of-work nonce |

**Total header size: 149 bytes** (v1 was 117 bytes).

The field order is fixed.  Any other order is non-canonical and produces a
non-canonical block hash.

---

## Header dictionary representation

```python
header = {
    "version": 2,
    "prev_hash": str,
    "merkle_root": str,
    "registry_root": str,
    "timestamp": int,
    "target": str,
    "nonce": int,
}
```

The `registry_root` value is a 64-character lowercase hex string.

---

## Block hash

The block hash is the double SHA-256 of the canonical header bytes.

```text
block_hash = SHA-256(SHA-256(encode_header_v2(header)))
```

Because the header format changed, every v2 block hash differs from a v1 hash
for the same logical content.  This is intentional and is part of the network
separation.

---

## Registry root semantics

For block at height `H`:

```text
header.registry_root = registry_root(State(B[0..H-1]))
```

That is, the header commits to the registry state *after* applying all blocks
before this one, but *before* applying this block's own governance transactions.

The transactions inside block `H` produce a new registry state, which becomes
the `registry_root` committed in block `H+1`.

Genesis block (`H=0`) commits to:

```text
header.registry_root = registry_root(
    RegistryState.genesis(
        governance_keys=GENESIS_GOVERNANCE_KEYS,
        threshold=GENESIS_THRESHOLD,
    )
)
```

because the genesis registry state includes the bootstrap governance authority
(Model B).

---

## Why commit to the *previous* state?

Two reasons:

1. **No circular dependency.**  The Merkle root already commits to the
   transactions in the block.  If the registry root also had to commit to the
post-transaction state, the header would depend on the transaction list twice
in different ways.  Committing to the pre-state keeps the header construction
linear.

2. **Light-client simplicity.**  A client validating block `H` only needs the
   registry state at the end of `H-1` to validate the attestations in `H`.
That state is committed in `H`'s header, so no extra round-trip is required.

---

## Governance transactions inside a block

A block may contain zero or more governance transactions of types:

* `curator_register`
* `curator_rotate`
* `curator_revoke`

They are encoded as ordinary transactions with type `registry` and are included
in the Merkle root like any other transaction.

The block admission procedure is:

```text
pre_state = state_at_end_of_previous_block
assert header.registry_root == registry_root(pre_state)

post_state = pre_state
for tx in block.transactions:
    if tx is a governance transaction:
        post_state = apply_registry_transaction(
            post_state,
            tx,
            block_height=H,
            txid=txid,
            context=governance_context(post_state)
        )

state_at_end_of_block = post_state
```

The `governance_context(post_state)` is derived from the active governance keys
in `post_state`.  For registration transactions on an empty state, the context
uses the genesis governance key set.

---

## Genesis v2

The v2 genesis block is a new block.  It cannot reuse v1 genesis values.

Required genesis constants:

```text
PROTOCOL_VERSION = 2
NETWORK_ID = "chainbreaker-scripture-v2"
GENESIS_MESSAGE = "Chain-Breaker v2 Genesis: ledger-derived curator governance"
GENESIS_TIMESTAMP = 1704067200  # same epoch as v1, or new value if network reset
GENESIS_TARGET = MAX_TARGET
GENESIS_NONCE = computed by brute force to satisfy target
GENESIS_HASH = computed from header bytes
GENESIS_MERKLE_ROOT = "0" * 64  # genesis has no transactions
GENESIS_REGISTRY_ROOT = registry_root(
    RegistryState.genesis(
        governance_keys=GENESIS_GOVERNANCE_KEYS,
        threshold=GENESIS_THRESHOLD,
    )
)
```

The genesis registry state includes the bootstrap governance key set and
threshold.  Governance keys are not a separate constant; they are the initial
registry state.

```text
GENESIS_GOVERNANCE_KEYS = [
    "hex_public_key_1",
    "hex_public_key_2",
    ...
]
GENESIS_THRESHOLD = N
```

The keys must be sorted lexicographically in the genesis specification so that
every node derives the same canonical state.  The threshold must satisfy
`1 <= N <= len(GENESIS_GOVERNANCE_KEYS)`.

Rationale: a governance-registration transaction needs to be signed by the
governance keys already in state.  Before any curator is registered, the only
available keys are the genesis keys.  Placing them in the initial registry
state keeps all authority inside the same state machine and avoids special-case
bootstrap logic after block 0.

---

## Protocol version and network ID

`chainbreaker-scripture-v2` requires:

* `PROTOCOL_VERSION` bump from `1` to `2`
* `NETWORK_ID` change from `chainbreaker-scripture-v1` to
  `chainbreaker-scripture-v2`
* package version bump to `0.3.0`

The network ID change prevents transaction replay across v1 and v2.

The protocol version change in the header prevents v1 nodes from accepting v2
blocks and vice versa.

---

## Migration and compatibility

There is no safe automatic migration from v1 to v2 because the header format
changed and every block hash would change.

Options:

1. **Network reset.**  Discard v1 chain state and mine a new v2 genesis.  This
   is the recommended option for an alpha prototype.

2. **Hard fork checkpoint.**  Define a v1 block height `H` after which v2
   rules apply.  Block `H+1` has `prev_hash` pointing to v1 block `H` but uses a
v2 header.  This is complex because v1 nodes cannot parse `H+1` and v2 nodes
must carry legacy validation logic.  Not recommended for this alpha stage.

Current recommendation: option 1, with explicit documentation that this is a
devnet/testnet reset, not a live upgrade.

---

## Files that must change in the implementation milestone

* `chainbreaker/block.py`
  * add `registry_root` to `BlockHeader`
  * bump `PROTOCOL_VERSION` to `2`
  * change `NETWORK_ID` to `chainbreaker-scripture-v2`
  * recompute genesis constants
  * update `BlockHeader.to_dict` / `from_dict`

* `chainbreaker/codec.py`
  * update `encode_header_v2` / `decode_header_v2`
  * keep v1 decoder available for tests or migration tools

* `chainbreaker/chain.py`
  * maintain per-chain-branch registry state
  * validate `header.registry_root` during `add_block`
  * derive registry state from replayed governance transactions
  * remove or deprecate `Registry`-based attestation validation

* `chainbreaker/witness.py`
  * validate attestations against historical registry state at the block
    height, not the current tip

* `chainbreaker/cli.py`
  * remove placeholder signer behavior
  * require valid attestations for mining
  * reject missing curator identities

* `tests/`
  * add header round-trip tests
  * add genesis v2 tests
  * add registry root recomputation tests
  * add historical attestation boundary tests
  * add fork/reorg registry rollback tests

---

## Test vectors required

The implementation milestone must include fixed vectors for:

1. Canonical empty `RegistryState` root.
2. Canonical v2 genesis header bytes and hash.
3. One valid `curator_register` transaction.
4. Registry state after one registration.
5. One valid `curator_rotate` transaction.
6. Registry state after rotation.
7. One valid `curator_revoke` transaction.
8. Registry state after revocation.
9. A v2 block header with valid `registry_root`.
10. A valid attestation at height before revocation.
11. An invalid attestation at height after revocation.

These vectors must be computed in at least two independent fresh processes and
must match exactly.

---

## Deferred decisions

* Difficulty retargeting algorithm remains unchanged in this milestone.
* Maximum block size and transaction count limits remain unchanged.
* Checkpoint format for fast sync is not defined here.
* P2P networking remains out of scope.

---

## Risks

* Changing the header format invalidates all existing v1 tests that depend on
  hard-coded genesis hashes or block hashes.  Those tests must be updated with
new v2 vectors.
* The `registry_root` validation path is hot; performance must be monitored
  when validating long chains.
* If the genesis governance private keys are lost, no curator can ever be
  registered.  This is acceptable for an alpha prototype but must be
  documented honestly.
