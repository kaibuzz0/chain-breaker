# Registry-Root Validation Design

Version: `chainbreaker-scripture-v2`  
Status: **design-only; no implementation changes**

---

## 1. Purpose

This document specifies how the ledger connects block headers to the
registry-state reducer defined in `chainbreaker/registry_state.py` and
`chainbreaker/governance.py`.

At this stage, every valid block must:

1. Satisfy proof-of-work (Milestone 4C).
2. Carry a `registry_root` that matches the deterministic registry state
   produced by all prior blocks.

This is the boundary between **valid blocks** and **valid state transitions**.

---

## 2. Core rule

For every block at height `H` (genesis is `H = 0`):

```text
block[H].header.registry_root == registry_root(state[H])
```

where:

```text
state[0] = RegistryState.genesis(governance_keys, threshold)
state[H] = apply_transactions(state[H-1], block[H].transactions, H)
```

The header commits to the **previous** state, not the state produced by its
own transactions.  This avoids a circular dependency: a block cannot include a
commitment to state transitions that depend on the block itself.

---

## 3. Validation order for a candidate block

When a node validates block `H` (for `H > 0`):

```text
1. Verify header format and version (v2 only).
2. Verify previous block exists and is valid.
3. Recompute previous registry state  state[H-1].
4. Verify block[H].header.registry_root == registry_root(state[H-1]).
5. Verify block[H].header.prev_hash == block[H-1].hash.
6. Verify timestamp rules (median past, future bound).
7. Verify proof-of-work against target.
8. Verify merkle root against block[H].transactions.
9. For each transaction in block[H].transactions, in order:
   a. If governance transaction, apply to a scratch copy of state[H-1].
   b. Validate signatures, network_id, schema_version, height rules.
   c. Detect duplicate IDs, duplicate keys, revoked keys, invalid rotations.
10. Compute resulting state[H].
11. Store state[H] keyed by block hash or height.
```

Genesis (`H = 0`) is special only in that it is a fixed constant.  Its
`registry_root` is verified against the hard-coded genesis state, not recomputed
from a previous block.

---

## 4. Transaction ordering rule

Transactions within a block are applied **strictly in list order**.

Rationale:

* Two different orderings of the same set of transactions can produce different
  registry states because a `curator_register(A)` followed by a
  `curator_revoke(A)` is valid, while the reverse is invalid (A is not yet
  registered).
* Archive transactions (`archive_add`) do not mutate registry state, but their
  ordering still matters for the Merkle root.

Therefore:

```text
block[H].merkle_root == MerkleTree([hash(tx) for tx in block[H].transactions])
```

and:

```text
state[H] = fold(apply_registry_transaction, state[H-1], block[H].transactions, H)
```

where `fold` preserves order.

---

## 5. Governance transaction validation in a block

Each governance transaction is validated before application:

```text
1. schema_version == 1
2. network_id == "chainbreaker-scripture-v2"
3. activation_height == H (or a fixed lookahead rule; see below)
4. signatures satisfy threshold using active governance keys at state[H-1]
5. transaction ID is unique within state[H-1]
6. public keys are 32-byte hex strings
7. rotation/revocation lineage is valid
```

Failure of any transaction causes the entire block to be rejected.

### Activation-height rule for this design

The existing reducer requires that a governance transaction included in block
`H` specifies an `activation_height` **strictly greater than** `H`:

```text
activation_height > H
```

This means the transaction is recorded in block `H` but the new key/record does
not become active until block `activation_height`.  A curator registered in
block `H` may therefore first be used for attestations at height
`activation_height` or later.

This rule preserves the reducer invariants already tested in Milestone 2 and
keeps 4D focused on chain integration rather than state semantics.  A future
design may introduce a different lookahead rule, but that requires an explicit
protocol change.

---

## 6. State storage model

### 6.1 Chosen model: height-indexed state cache

The ledger stores `state[H]` for each accepted height `H`.

```text
Ledger:
    chain: list[Block | BlockV2]
    registry_states: dict[int, RegistryState]
```

### 6.2 Initialization

```text
registry_states[0] = RegistryState.genesis(governance_keys, threshold)
```

### 6.3 Block acceptance

When block `H` is accepted:

```text
registry_states[H] = apply_transactions(registry_states[H-1], block[H].transactions, H)
```

### 6.4 Determinism requirement

The cache must be a pure function of the chain.  Dropping the cache and
replaying the chain from genesis must reproduce exactly the same `state[H]` for
every height.

### 6.5 No global mutable state

No module-level `global_registry_state` is allowed.  Every chain instance owns
its own `registry_states` dictionary, and two different `Ledger` objects must
be able to hold different states simultaneously.

---

## 7. Fork and reorganization compatibility

### 7.1 No reorg engine in 4D

Milestone 4D does **not** implement chain reorganizations.  The ledger accepts
blocks only on the current best chain.

### 7.2 Reorg-safe design constraints

To avoid making future reorgs impossible, the implementation must:

1. Store `registry_states` keyed by height, not by a single `current_state`
   variable.
2. Never mutate `registry_states[H-1]` when computing `registry_states[H]`.
3. Allow a future reorg to discard all `registry_states[H > reorg_height]`
   and replay the alternate chain from that height.

### 7.3 Reorg replay sketch (for future milestones)

```text
def reorg_to_height(new_tip, common_height):
    discard all registry_states[H > common_height]
    for H from common_height + 1 to len(new_chain) - 1:
        validate block[H] against registry_states[H-1]
        registry_states[H] = apply_transactions(registry_states[H-1], block[H].transactions, H)
```

This is documented here but not implemented.

---

## 8. Failure cases and responses

| Condition | Response |
| --------- | -------- |
| `registry_root` mismatch | Reject block |
| Invalid governance signature | Reject block |
| Duplicate curator ID | Reject block |
| Duplicate public key | Reject block |
| Revoked key used | Reject block |
| Invalid rotation lineage | Reject block |
| `activation_height` != H | Reject block |
| Wrong `network_id` | Reject block |
| Wrong `schema_version` | Reject block |
| Governance transaction with non-governance type | Reject block |
| Merkle root mismatch | Reject block |
| PoW failure | Reject block (4C) |
| Timestamp violation | Reject block |

---

## 9. Validation invariants

The following invariants must hold at all accepted heights:

```text
I1. registry_states[0] == RegistryState.genesis(governance_keys, threshold)
I2. For H > 0: block[H].header.registry_root == registry_root(registry_states[H-1])
I3. registry_states[H] == apply_transactions(registry_states[H-1], block[H].transactions, H)
I4. block[H].header.merkle_root == MerkleRoot(block[H].transactions)
I5. int(block[H].hash, 16) <= block[H].header.target
I6. block[H].header.prev_hash == block[H-1].hash
I7. No two accepted blocks at the same height have different registry states.
```

---

## 10. Test plan for 4D

### 10.1 Unit tests

- Genesis state matches `GENESIS_REGISTRY_ROOT`.
- Block with correct `registry_root` is accepted.
- Block with wrong `registry_root` is rejected.
- Governance transaction accepted when signatures are valid.
- Governance transaction rejected when signatures are invalid.
- Duplicate curator ID rejected.
- Duplicate public key rejected.
- Revoked key cannot attest.
- Activation height mismatch rejected.
- Archive transactions do not change registry state but still affect Merkle root.

### 10.2 Replay tests

- Delete `registry_states` and recompute from genesis; assert equality.
- Build a chain of several blocks; verify every `registry_root` in every header.

### 10.3 Adversarial tests

- Mutate `registry_root` in a mined block; assert rejection.
- Mutate a governance transaction after mining; assert Merkle root mismatch.
- Reorder transactions in a block; assert state change.

---

## 11. Scope for Milestone 4D

### Implement

- `Ledger` stores `registry_states` keyed by height.
- `Ledger.add_block_v2()` validates and accepts v2 blocks with registry-root
  checks.
- Governance transactions inside blocks are validated and applied.
- Chain replay recomputes registry states deterministically.

### Do not implement

- Reorganization engine.
- CLI commands for registry queries.
- Historical witness validation (Milestone 4E).
- Performance optimization.
- Lookahead activation heights.
- P2P, networking, or external consensus.

---

## 12. References

* `docs/PROTOCOL.md` — Protocol v2 specification
* `docs/HEADER_V2_DESIGN.md` — v2 header layout
* `docs/CONSENSUS_INVARIANTS.md` — consensus invariants
* `docs/GENESIS_V2_SPECIFICATION.md` — genesis constants
* `docs/POW_V2_SPECIFICATION.md` — PoW rules
* `chainbreaker/registry_state.py` — deterministic state reducer
* `chainbreaker/governance.py` — governance transaction models
