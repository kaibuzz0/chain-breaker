# Phase 7H — Reorg / State-Branching Implementation Report

## Summary

Implemented the deterministic reorganization and competing-branch mechanics
specified in Phase 7G, without introducing networking, settlement, smart
contract, or Protocol V2 consensus changes.

The canonical state continues to equal the deterministic replay of the valid
branch with the greatest accumulated work. Branch evaluation is isolated from
canonical state until an atomic tip switch commits the new HEAD.

## Files Changed

### New

- `chainbreaker/reorg.py`
  - `BranchCandidate` abstraction
  - `ReorgError`
  - `ReorgEngine`
  - `ReorgResult`
  - `find_common_ancestor`
  - `compute_work`
  - `compare_work`
  - scratch-state replay and candidate validation

### Modified

- `chainbreaker/storage/backend.py`
  - `read_chain_up_to`
  - `list_blocks`
  - `atomic_tip_switch` (journals commit, rebuilds indexes)
  - `rebuild_indexes`
  - `read_snapshot` now rejects snapshots above canonical HEAD

### Tests Added

- `tests/test_reorg_fork_choice.py` (11 tests)
- `tests/test_reorg_state_isolation.py` (3 tests)
- `tests/test_reorg_storage.py` (5 tests)
- `tests/test_reorg_attestations.py` (2 tests)
- `tests/test_reorg_snapshots.py` (3 tests)

Total new reorg tests: **24**.

## Fork-Choice Algorithm

1. Find the deterministic common ancestor of current and candidate chains.
2. Reject genesis mismatch outright.
3. Validate the candidate suffix in scratch space:
   - prev-hash linkage
   - Header V2 version
   - PoW against target
   - expected target
   - Merkle root
   - registry-root commitments
   - governance transaction validity
   - timestamp monotonicity and MTP window checks
4. Compute total valid accumulated work on the candidate suffix.
5. Compare to current-chain accumulated work.
6. Switch only if candidate work is strictly greater.

## Equal-Work Rule

No automatic tip change on equal accumulated work. A reorg is triggered only
when `candidate_work > current_work`. Local arrival order does not influence
fork choice.

## Branch-State Isolation Strategy

`ReorgEngine._state_at` replays registry state from the common ancestor on the
current chain. Candidate validation uses a fresh `RegistryState` instance
inside `validate_candidate_suffix`. The canonical `Ledger`/storage state is not
touched during evaluation. If validation fails, the canonical store remains
unchanged.

## Storage / Tip-Switch Behavior

- `atomic_tip_switch` writes a `JOURNAL_COMMIT` record before updating HEAD.
- HEAD is atomically rewritten.
- Derived indexes are rebuilt from the new canonical chain.
- Orphaned block/header/snapshot files are left on disk but no longer referenced
  by HEAD or indexes.
- `read_snapshot` returns `None` for heights above the canonical HEAD.

## Attestation / Archive Semantics

- Attestation cryptographic validity is separate from canonical-chain inclusion.
- An attestation signed by a curator remains cryptographically valid against the
  historical registry state of its own branch.
- After a reorg, the same attestation does not verify against the canonical
  registry if its curator is not active on the winning branch.
- Archive objects are content-addressed and remain locally cached; only the
  canonical provenance chain changes.

## Verification

| Check | Status |
|-------|--------|
| ruff (chainbreaker + tests) | passing |
| mypy chainbreaker | passing |
| bandit chainbreaker/reorg.py + storage/backend.py | passing |
| pip-audit -r requirements.txt | no known vulnerabilities |
| python -m build --wheel | passing |
| reorg test suites (24 tests) | passing |
| storage backend/recovery tests | passing |
| full pytest suite | not run to completion locally due to very slow PoW tests in `test_storage_multiblock.py` and `test_storage_locking.py` |

## Bugs Discovered

- Initial test helpers computed `registry_root` as the post-block state instead
  of the pre-block state, causing candidate validation to fail. Fixed by
  setting the header's `registry_root` to the state BEFORE applying the block's
  transactions, matching `chain.py` semantics.
- `read_snapshot` did not bound snapshot eligibility by canonical HEAD; fixed
  so orphaned snapshots cannot be trusted as canonical state.

## Protocol V2 Behavior

**No frozen Protocol V2 semantics were changed.** The reorg engine is an
additive, non-consensus consumer of the existing block, chain, governance, and
storage modules. Validation reuses the existing rules rather than redefining
them.

## Unresolved Risks / Phase 7I Work

- Crash during `atomic_tip_switch` between JOURNAL_COMMIT and HEAD update.
- Corrupt candidate branch files causing validation failure.
- State contamination attempts from orphaned indexes/snapshots.
- Deep competing forks beyond local `max_reorg_depth`.
- Concurrent append / reorg races (single-writer discipline is assumed).
- Recovery semantics in `recover_store` return the prev_hash of the lowest
  verified block, not the verified block hash; this is pre-existing behavior
  and will be evaluated under Phase 7I.

## Test Count

- New reorg tests: 24
- Total project tests: expanded from previous count by 24.

## Recommended Final Commit

`implement deterministic reorg and branch-state switching`
