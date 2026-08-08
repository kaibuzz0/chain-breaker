# Reorg State Machine

Version: chainbreaker-scripture-v2  
Status: **design-only milestone**  
Branch: `phase7g-reorg-state-branching-design`

---

## 1. State definitions

| State | Description |
|-------|-------------|
| `SYNCED` | Canonical tip is the known best branch; node is idle. |
| `HEADER_PENDING` | A new candidate header has been received and is queued for validation. |
| `VALIDATING_HEADER` | The candidate header's PoW, syntax, and linkage are being checked. |
| `FETCHING_BRANCH` | The candidate tip links to a block we do not yet have; we are fetching missing ancestors. |
| `REPLAYING_CANDIDATE` | The connect set is being replayed to derive candidate registry state. |
| `COMPARING_WORK` | Both branches have valid state; accumulated work is compared. |
| `PREPARING_SWITCH` | The candidate branch has more work; we are staging the atomic tip switch. |
| `SWITCHING_TIP` | `HEAD` is being atomically updated to the candidate tip. |
| `REBUILDING_DERIVED` | Indexes and snapshots are being rebuilt for the new canonical chain. |
| `ROLLBACK` | An error occurred; any partial candidate state is discarded and node returns to `SYNCED` or `FETCHING_BRANCH`. |

---

## 2. Transitions

### 2.1 `SYNCED` → `HEADER_PENDING`

**Trigger:** A new candidate header or block arrives (from any source — future network, local test, CLI).

**Action:**

- Parse header; reject immediately if malformed.
- Check basic PoW and version.
- Enqueue for full validation.

**Guards:**

- Header version must equal 2.
- Header must be 149 bytes.
- `hash(header) <= target`.

### 2.2 `HEADER_PENDING` → `VALIDATING_HEADER`

**Trigger:** Queue handler selects the candidate.

**Action:**

- Verify PoW exactly (double-SHA256 on canonical bytes).
- Verify `prev_hash` is known locally or is marked as fetchable.

**Guards:**

- PoW must be valid.
- `prev_hash` must not be the zero hash except for genesis.

### 2.3 `VALIDATING_HEADER` → `SYNCED` (simple extension)

**Trigger:** `prev_hash` equals current canonical tip hash.

**Action:**

- Validate full block if block body is present.
- Derive new registry state.
- Append via `StorageBackend.append_block` (atomic commit).
- New `SYNCED` state: tip = candidate tip.

**Guards:**

- Full block validation passes.
- Registry root matches derived state.
- Accumulated work increases monotonically because height increased on same branch.

### 2.4 `VALIDATING_HEADER` → `FETCHING_BRANCH`

**Trigger:** `prev_hash` is known but is not the current tip; candidate height is greater than current tip or equal work may be possible.

**Action:**

- Request missing ancestors up to a common ancestor (future network) or walk backward over local data.
- Maintain a bounded fetch window (local policy).

**Guards:**

- Candidate tip height must not exceed `current_height + max_fetch_ahead` if enforced.
- Stop at genesis if no common ancestor found.

### 2.5 `FETCHING_BRANCH` → `REPLAYING_CANDIDATE`

**Trigger:** All blocks from common ancestor's child to candidate tip are available.

**Action:**

- Load common ancestor state (from snapshot or replay).
- Apply connect-set transactions in order, producing candidate registry state per height.
- Verify each block's registry root commitment.

**Guards:**

- Every block in connect set validates.
- No state object from the current canonical suffix is reused.

### 2.6 `REPLAYING_CANDIDATE` → `COMPARING_WORK`

**Trigger:** Replay completes and candidate branch is fully valid.

**Action:**

- Compute `work(candidate)` from common ancestor to candidate tip.
- Compute `work(current)` from common ancestor to current tip.

**Guards:**

- Both branch states are fully deterministic.

### 2.7 `COMPARING_WORK` → `SYNCED` (ignore candidate)

**Trigger:** `work(candidate) <= work(current)`.

**Action:**

- Discard candidate branch state if not configured to persist alternate branches.
- Optionally retain headers/blocks in `branches/` for later.
- Remain on current canonical tip.

**Guards:**

- Work comparison is exact (integer arithmetic).

### 2.8 `COMPARING_WORK` → `PREPARING_SWITCH`

**Trigger:** `work(candidate) > work(current)` and common ancestor is within `max_reorg_depth`.

**Action:**

- Identify disconnect set (`current_height` down to `common_ancestor_height + 1`).
- Identify connect set (`common_ancestor_height + 1` to `candidate_height`).
- Confirm connect-set blocks are durable.
- Prepare new `HEAD` bytes.

**Guards:**

- All connect-set blocks have journal `COMMIT` records.
- `max_reorg_depth` policy satisfied.

### 2.9 `PREPARING_SWITCH` → `SWITCHING_TIP`

**Trigger:** Atomic `HEAD` write is ready.

**Action:**

- Write new `HEAD` atomically via `os.replace` / atomic write.
- Fsync `HEAD` and its parent directory.

**Guards:**

- No concurrent writer holds the single-writer lock.
- New `HEAD` must reference a fully durable block.

### 2.10 `SWITCHING_TIP` → `REBUILDING_DERIVED`

**Trigger:** `HEAD` is durable.

**Action:**

- Delete or quarantine indexes and snapshots inconsistent with new `HEAD`.
- Rebuild `height_to_hash` and `hash_to_height` indexes.
- Optionally rebuild the nearest snapshot.

**Guards:**

- Derived rebuild must not touch canonical block/header files.
- If rebuild fails, recovery can rebuild from canonical data on next startup.

### 2.11 `REBUILDING_DERIVED` → `SYNCED`

**Trigger:** Indexes and snapshots are consistent with new canonical chain.

**Action:**

- Emit reorg event (height, old tip, new tip, disconnect count, connect count).
- Return to idle.

### 2.12 Any state → `ROLLBACK`

**Trigger:** Validation failure, missing data, work comparison lost, I/O error, or policy rejection.

**Action:**

- Discard scratch candidate state.
- Leave canonical tip unchanged.
- Log reason.
- Return to `SYNCED` (or to `FETCHING_BRANCH` if more candidates remain).

---

## 3. State invariants

| State | Invariant |
|-------|-----------|
| `SYNCED` | `HEAD` points to the valid branch of greatest known work. All derived data is consistent. |
| `HEADER_PENDING` | Candidate header is queued; `HEAD` and derived data are unchanged. |
| `VALIDATING_HEADER` | `HEAD` unchanged; candidate not yet accepted. |
| `FETCHING_BRANCH` | `HEAD` unchanged; missing ancestors are being fetched or located. |
| `REPLAYING_CANDIDATE` | `HEAD` unchanged; candidate state is computed in scratch space. |
| `COMPARING_WORK` | `HEAD` unchanged; both branch states are valid and deterministic. |
| `PREPARING_SWITCH` | `HEAD` unchanged; connect set is durable. |
| `SWITCHING_TIP` | `HEAD` write is in progress. Old `HEAD` is still valid if write fails. |
| `REBUILDING_DERIVED` | New `HEAD` is durable. Derived data may be temporarily inconsistent. |
| `ROLLBACK` | `HEAD` unchanged from before the candidate arrived. |

---

## 4. Concurrency and locking

A single node must hold exactly one canonical writer. The existing `SingleWriterLock` from `chainbreaker/storage/filesystem.py` covers the storage backend.

During a reorg:

- The writer lock must be held before any candidate state is promoted.
- If a candidate arrives while another candidate is being processed, it is queued.
- The lock is released only after `REBUILDING_DERIVED` completes or `ROLLBACK` finishes.

---

## 5. Error handling

| Failure | Response |
|---------|----------|
| Candidate header invalid | Reject; log. |
| Missing ancestor and fetch fails | Stay in `FETCHING_BRANCH` or roll back. |
| Connect-set block fails validation | Roll back. |
| Registry root mismatch | Roll back; mark candidate branch invalid. |
| Work not greater | Ignore candidate. |
| `max_reorg_depth` exceeded | Reject candidate; log. |
| Atomic `HEAD` write fails | Roll back; storage recovery on next startup will pick the old `HEAD` or roll back further. |
| Index rebuild fails | New `HEAD` is still canonical; recovery will rebuild indexes on next startup. |

---

## 6. Future network-layer handshake

When networking is designed (after Phase 7I), the following messages map to this state machine:

| Message | Maps to |
|---------|---------|
| `inv` (new block hash) | enqueue `HEADER_PENDING` |
| `headers` (candidate headers) | `VALIDATING_HEADER` / `FETCHING_BRANCH` |
| `getdata` (block request) | data plane, not state machine |
| `block` (full block) | `VALIDATING_HEADER` → extension or `FETCHING_BRANCH` → replay |
| `getheaders` | index lookup service |
| `getblocks` | block delivery service |

This document does not define wire formats; it defines the consensus-side state machine that wire handlers will drive.
