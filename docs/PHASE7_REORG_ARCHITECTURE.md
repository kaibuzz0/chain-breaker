# Phase 7G — Reorg and State-Branching Architecture

Version: chainbreaker-scripture-v2  
Status: **design-only milestone**  
Branch: `phase7g-reorg-state-branching-design`  
Base commit: `fc693f519a9f387f2111ff780c0362844cf5898a`

---

## 1. Purpose

This document defines how a single Chain-Breaker node selects, validates, and switches between competing valid histories (reorganizations, or "reorgs") while preserving Protocol V2 consensus invariants and durable-storage guarantees.

This phase is **design only**. No implementation code changes are made to:

- Protocol V2 consensus rules (`chainbreaker/block.py`, `chainbreaker/registry_state.py`, `chainbreaker/governance.py`, `chainbreaker/codec.py`)
- Canonical block/header serialization
- Genesis constants
- Proof-of-work target logic
- Registry root derivation
- Attestation cryptography

---

## 2. Core invariant

```text
canonical state == deterministic replay of the valid branch with greatest accumulated work
```

Height alone must never decide the canonical branch. A reorg is warranted only when an alternative branch demonstrates strictly greater accumulated proof-of-work than the current canonical tip.

A branch is **valid** when every block in it:

1. satisfies Protocol V2 proof-of-work (`hash <= target`);
2. links to its predecessor via `prev_hash`;
3. carries a `registry_root` matching the deterministic replay of all governance transactions up to and including that block;
4. respects median-past time, target retargeting, size limits, and all other consensus rules;
5. is fully durable on disk (journal `COMMIT` + canonical files + HEAD).

---

## 3. Glossary

| Term | Meaning |
|------|---------|
| **Branch** | A linear sequence of blocks beginning at the same genesis and ending at some tip. |
| **Tip** | The highest block in a branch. |
| **Accumulated work** | Sum of `2**256 / (target + 1)` over every block in the branch. More work ~= harder chain. |
| **Common ancestor** | The highest block shared by two branches. |
| **Orphaned branch** | A previously canonical branch that is no longer canonical after a reorg. |
| **Candidate branch** | An alternative branch being evaluated for promotion. |
| **Canonical tip** | The tip of the branch currently selected as authoritative. |
| **Disconnect set** | Blocks removed from the canonical chain during a reorg. |
| **Connect set** | Blocks added to the canonical chain during a reorg. |

---

## 4. Reorg state machine

```text
                 +------------------+
                 |  Idle / Synced   |
                 +---------+--------+
                           |
              candidate block(s) received / discovered
                           v
                 +------------------+
    +----------->|  Validate Header |
    |            +---------+--------+
    |                      | valid?
    |            no        | yes
    |            v         v
    |   +--------+---+  +--+---------+
    |   |   Reject   |  | Find Common |
    |   +------------+  |  Ancestor   |
    |                   +------+------+
    |                          |
    |                          v
    |                   +------+------+
    |                   | Replay Branch|
    |                   |  State (fork) |
    |                   +------+------+
    |                          |
    |                          v
    |                   +------+------+
    |                   | Compare Work|
    |                   +------+------+
    |                          |
    |              candidate <= current
    |                    |     | candidate > current
    |                    v     v
    |            +-------+  +--+---------+
    +-----------| Ignore |  | Atomic Tip|
                |        |  |   Switch   |
                +--------+  +-----+------+
                                  |
                                  v
                          +-------+--------+
                          | Rebuild Derived |
                          | Indexes/Snapshots|
                          +-------+--------+
                                  |
                                  v
                          +-------+--------+
                          |  Idle / Synced  |
                          +-----------------+
```

---

## 5. Reorg algorithm

### 5.1 Candidate validation

For each candidate tip block `B_tip`:

1. Verify header PoW.
2. Verify `prev_hash` exists in local storage (either canonical or another known branch).
3. If `B_tip.prev_hash` equals the current canonical tip hash, the candidate is a simple extension.
4. Otherwise, walk backward through `prev_hash` links until either genesis or a common ancestor is found.
5. Collect the list of candidate blocks from the common ancestor's child to `B_tip`. This is the **connect set**.
6. Validate each block in the connect set in height order, including registry-root commitments.

A candidate branch that fails validation anywhere is rejected entirely. A partially validated branch is never partially accepted.

### 5.2 Common-ancestor discovery

Given two tips `T_current` and `T_candidate`:

1. Collect ancestors of `T_current` into a hash set (`ancestors_current`).
2. Walk backward from `T_candidate`; the first block found in `ancestors_current` is the common ancestor.
3. The height difference between the common ancestor and a tip is the **branch length** from that side.

Optimization: for long chains, skip using height buckets (store known headers indexed by height) is permitted, but the discovered common ancestor must always be verified by hash continuity.

### 5.3 Branch-specific registry state

Registry state is a pure function of chain history:

```text
state_at(H) = apply_block_transactions(state_at(H-1), block_H)
```

During a reorg, the candidate branch's registry state must be derived independently from the common ancestor's state:

```text
candidate_state = replay(common_ancestor_state, connect_set)
current_state   = replay(common_ancestor_state, current_branch_suffix)
```

No state from the current branch after the common ancestor may leak into the candidate branch, and vice versa.

The registry root in each candidate block header must match `registry_root(candidate_state_at(height))`. Any mismatch invalidates the branch.

### 5.4 Accumulated-work comparison

Compute work for current and candidate branches from the common ancestor to each tip:

```text
work(branch) = sum over blocks in branch of (2**256 // (target + 1))
```

Promote candidate only if:

```text
work(candidate) > work(current)
```

Equal work must not trigger a reorg. The current canonical branch retains authority to avoid oscillation.

---

## 6. Storage interaction

### 6.1 Authoritative data

Only canonical block/header files are authoritative. A reorg must not treat journal records, HEAD, snapshots, or indexes as authoritative for branch selection.

### 6.2 Atomic tip switch

The canonical tip is advanced by writing a new `HEAD` atomically. During a reorg:

1. Do not delete disconnect-set blocks immediately.
2. Ensure connect-set blocks are fully durable (each has its own `COMMIT` record and canonical files).
3. Atomically write `HEAD` to the new tip.
4. After `HEAD` is durable, delete or move derived indexes and snapshots that refer only to the orphaned branch.
5. Rebuild indexes from the new canonical chain.

### 6.3 Snapshot and index invalidation

Snapshots and indexes are derived accelerators only. After a reorg:

- Snapshots above the new common ancestor and below/above the old tip may be stale and must be discarded or re-verified.
- Indexes (`height_to_hash`, `hash_to_height`) must be rebuilt from canonical files.
- In-memory caches must be invalidated.

### 6.4 Crash recovery during reorg

A crash may occur while both disconnect-set and connect-set blocks exist on disk. Recovery must:

1. Read the durable `HEAD`. If `HEAD` is missing or malformed, recover using the Phase 7F rule (`safe_height = min(HEAD, last_commit)`).
2. Treat the recovered `HEAD` as the canonical tip.
3. Delete any derived files (indexes, snapshots, stale `HEAD` updates) that are inconsistent with the recovered `HEAD`.
4. Rebuild indexes from canonical blocks.
5. Never leave the node with two competing tips.

### 6.5 Alternate-branch storage

Before a candidate branch is promoted, its blocks may be stored durably as **non-canonical branch data** in a separate subtree, e.g.:

```text
branches/{branch_id}/headers/{height}.hdr
branches/{branch_id}/blocks/{height}.bin
```

Storage of alternate branches is optional and local-policy controlled. If stored, they must be clearly distinguished from canonical data and must not influence `HEAD` or consensus state until promoted.

---

## 7. Historical attestation behavior

Attestations are signatures over `(body_hash, curator_id, block_height)`. Their validity depends on the registry state at `block_height`.

After a reorg:

- Attestations made on blocks that remain in the new canonical branch retain their validity if the registry state at that height is unchanged.
- Attestations made only on orphaned blocks become **historical**; they may still be verifiable if the curator was active at that height, but they no longer prove anything about the current canonical branch.
- The node must never automatically invalidate an attestation merely because its block was orphaned. Validity is a function of the registry state at the claimed height, not of current tip preference.

---

## 8. Archive-object behavior

Archive objects are content-addressed and immutable. A reorg does not alter archive bytes.

- Manifests committed in blocks of the orphaned branch remain stored and verifiable.
- A block in the new canonical branch may reference the same archive object as an orphaned block; content-addressing makes this safe.
- Pruning of archive objects must never remove content referenced by any unrevoked attestation on any known branch.

---

## 9. Maximum reorg depth

Maximum reorg depth is a **local policy**, not a Protocol V2 consensus rule. A node may configure:

```text
max_reorg_depth = N blocks
```

If the common ancestor is more than `N` blocks behind the current tip, the node refuses the reorg. This protects against deep-rewrite attacks but may also prevent the node from catching up to the true longest chain.

Default policy will be defined in Phase 7H implementation. It must be overrideable by the operator.

---

## 10. Networking integration (future)

Phase 7G does not design or implement networking. It does, however, define the interface that a future network layer will call:

```text
on_candidate_block(block_bytes) -> Accept | Reject | Reorg
on_candidate_header(header_bytes) -> Accept | Reject | RequestBlock
get_common_ancestor(hash) -> height | None
get_headers(locator_hashes, count) -> [header_bytes]
get_blocks(start_height, count) -> [block_bytes]
```

All network-provided candidates pass through the same validation and work-comparison pipeline.

---

## 11. Security considerations

| Threat | Mitigation |
|--------|------------|
| Low-work branch flood | Reject candidates with `work <= current_work`; rate-limit header processing. |
| Deep rewrite | Local `max_reorg_depth` policy; checkpoints; manual operator override. |
| State contamination during replay | Derive candidate state in a scratch object; do not mutate canonical state until switch. |
| Partially durable reorg | Atomic `HEAD` update only after all connect-set blocks are durable. |
| Orphaned-state leak | Disconnect-set state objects discarded; indexes rebuilt. |
| Timestamp / median-past gaming | Full block validation on candidate branch. |
| Malicious snapshot | Snapshots are accelerators; replay from canonical blocks wins. |

---

## 12. Open design questions for Phase 7H

1. Should alternate branches be persisted durably, kept only in memory, or kept only as header skeletons until promotion?
2. What is the default `max_reorg_depth` and how is it exposed in config?
3. Should the node support explicit checkpoints that override work comparison?
4. How should the storage backend expose `get_block_locator` and `get_headers` to a future network layer?
5. Should reorg events be logged to a dedicated audit file?

---

## 13. Relationship to other documents

- `docs/adr/004-storage-backend-boundary.md` — defines the `StorageBackend` interface that performs atomic commits.
- `docs/adr/005-snapshot-and-pruning-model.md` — defines snapshot invalidation and rebuild rules.
- `docs/adr/006-write-ahead-journal.md` — defines durable commit boundaries used during reorg.
- `docs/REORG_STATE_MACHINE.md` — detailed state-machine transitions.
- `docs/REORG_ADVERSARIAL_REVIEW.md` — adversarial scenarios and mitigations.
