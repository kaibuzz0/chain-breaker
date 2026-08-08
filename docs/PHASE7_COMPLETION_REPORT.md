# Phase 7 Completion Report

## Verification checkpoint

**Date:** 2026-08-08  
**Branch:** `main`  
**HEAD:** `68123bf7fa1c214855dc908ea18d3f85bb9a677e`  
**origin/main:** `68123bf7fa1c214855dc908ea18d3f85bb9a677e`  
**Working tree:** clean  

Phase 7H and Phase 7I have both been merged to `main` via:

- PR #31 — `phase7h-reorg-state-branching-implementation`
- PR #32 — `phase7i-reorg-fault-and-fork-certification`

## Phase 7 timeline

| Phase | Title | Status | Merge |
|-------|-------|--------|-------|
| 7A | Durable storage architecture | completed | merged |
| 7B | Language-neutral vectors | completed | merged |
| 7C | Independent Rust verifier | completed | merged |
| 7D | Consensus mutation testing | completed | merged |
| 7E | Durable storage implementation | completed | merged |
| 7F | Storage restart / fault certification | completed | merged |
| 7G | Reorg architecture design | completed | merged |
| 7H | Deterministic reorg implementation | completed | **PR #31** |
| 7I | Reorg fault and fork certification | completed | **PR #32** |

## What Phase 7H delivered

- `chainbreaker/reorg.py` — deterministic reorganization engine
  - `BranchCandidate`, `ReorgResult`, `ReorgEngine`
  - accumulated-work fork choice (never height alone)
  - branch-specific `RegistryState` replay from common ancestor
  - candidate validation: linkage, version, PoW, target, Merkle root,
    registry-root commitments, governance transactions, historical witnesses
  - atomic tip-switch preparation

- `chainbreaker/storage/backend.py` extensions
  - `read_chain_up_to`, `list_blocks`
  - `atomic_tip_switch`
  - `rebuild_indexes`
  - `read_snapshot` rejects orphaned snapshots above HEAD

- `docs/PHASE7H_REORG_IMPLEMENTATION_REPORT.md`
- 24 reorg tests across five files

## What Phase 7I delivered

- `docs/REORG_CERTIFICATION_INVARIANTS.md` — 13 explicit invariants
- `docs/PHASE7I_REORG_CERTIFICATION_REPORT.md` — certification methodology
- Additional attack tests:
  - `tests/test_reorg_head_corruption.py` — HEAD corruption recovery
  - `tests/test_reorg_archive_provenance.py` — archive object immutability
  - `tests/test_reorg_snapshot_attacks.py` — orphaned/corrupt snapshot rejection

## Protocol V2 freeze preserved

- No changes to `chainbreaker/block.py`
- No changes to `chainbreaker/consensus/protocol_v2.py`
- No changes to `chainbreaker/codec.py`
- No changes to `chainbreaker/crypto.py`
- No changes to `vectors/`
- No frozen test vectors modified
- No consensus serialization changes

## Verification results (local, CI-equivalent)

| Gate | Result |
|------|--------|
| `ruff check chainbreaker tests` | passing |
| `mypy chainbreaker` | passing |
| `bandit -r chainbreaker/reorg.py chainbreaker/storage/backend.py` | passing |
| `python -m build --wheel` | passing |
| `pip-audit -r requirements.txt` | no known vulnerabilities |
| Phase 7H/7I reorg tests (24) | passing |
| Storage tests (52, excluding slow PoW stress tests) | passing |

## Core invariants now certified

From `docs/REORG_CERTIFICATION_INVARIANTS.md`:

1. **Durable HEAD** — `JOURNAL_COMMIT` before `HEAD` rewrite.
2. **Isolated branch evaluation** — candidate replay uses scratch state.
3. **Deterministic fork choice** — greatest accumulated valid work.
4. **Validity precedes work** — invalid candidates cannot win.
5. **Registry follows winner** — canonical state replays the winning branch.
6. **Orphaned attestations are not canonical** — validity != inclusion.
7. **Archive objects are immutable** — content-addressed, branch-independent.
8. **Snapshots above HEAD untrusted** — height-bound snapshot reads.
9. **Derived indexes rebuilt atomically** — after tip switch.
10. **No hybrid state after restart** — recovery yields old or new chain.
11. **Reorg depth is local policy** — not consensus.
12. **Common ancestor is deterministic** — genesis mismatch rejected.
13. **Reorg can be reversed** — old branch can regain canonical status.

## Known limitations and deferred work

These are explicitly not blockers for Phase 7 completion; they belong to the
next design phase.

1. **End-to-end node crash matrix.** The storage engine has failpoints and
   journal-ordered reorg commits, but the full node path that persists candidate
   blocks, switches HEAD, and rebuilds indexes is not yet wired as a single
   orchestrator. That belongs to Phase 8 / networking-prep.
2. **Timestamp/MTP in candidate validator.** `validate_candidate_suffix`
   currently delegates timestamp rules to `Ledger.validate_chain` at the node
   layer. A direct check can be added when the node path is formalized.
3. **Long-fork retarget projection.** `_expected_target_at` assumes the
   current tip's target for short forks; deep retarget-boundary forks need
   target projection.
4. **Concurrent candidate evaluation.** `ReorgEngine` is stateless; a node
   orchestrator will serialize/queue candidates.
5. **Competing archive provenance manifests.** The test verifies object
   immutability; canonical provenance tracking belongs to the node layer.

## What remains before networking

Phase 7 closes the internal chain-state hardening arc. Before networking
implementation, the next required phase is:

**Phase 8 — Protocol boundary audit for distributed operation**

Design-only deliverables:

1. Wire protocol specification
2. Peer identity model
3. Block announcement / sync protocol
4. Adversarial network threat model
5. P2P message schema using existing V2 serialization
6. Bootstrap / discovery policy (or explicit lack thereof)
7. Network partition behavior

No networking code should be implemented until Phase 8 design is reviewed and
approved.

## Conclusion

Phase 7 is complete. The Chain-Breaker core now provides:

- deterministic Protocol V2 consensus
- independent Rust verification
- mutation-tested correctness
- durable, journal-backed storage
- crash recovery
- reorganization with branch-state isolation
- adversarial certification of reorg invariants

The project has crossed from single-node archival prototype to a verifiable
blockchain protocol core. Phase 8 will define how that core behaves under
networked operation.

**Protocol V2 freeze preserved.**
