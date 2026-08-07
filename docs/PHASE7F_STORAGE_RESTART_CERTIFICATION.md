# Phase 7F — Storage Restart Certification

## Goal

Prove that the Chain-Breaker durable store always restarts into one
deterministic valid state after crashes, partial writes, journal corruption,
HEAD corruption, snapshot corruption, index corruption, archive corruption,
repeated recovery, and process interruption.

## Base commit

`5a67d8f465bdf91185fcb4aeeaec9f22d0bed990`

## Branch

`phase7f-storage-restart-certification`

## Files added / changed

- `chainbreaker/storage/backend.py` — extended failpoint matrix
- `tests/test_storage_fault_matrix.py` — commit-step fault matrix (28 failpoints)
- `tests/test_storage_multiblock.py` — 100-block and randomized fault sequences
- `tests/test_storage_corruption.py` — journal/HEAD/snapshot/index/archive corruption
- `tests/test_storage_locking.py` — single-writer lock tests
- `tests/test_storage_performance.py` — latency baseline
- `tests/test_storage_recovery.py` — updated with additional corruption cases
- `storage-vectors/` — Storage Format V1 golden vectors
- `docs/PHASE7F_STORAGE_RESTART_CERTIFICATION.md` — this report

## 1. Commit-step fault matrix

Injected failure at every durable commit boundary:

```text
before_begin
after_begin
before_header_stage
after_header_stage
after_header_staged_record
before_block_stage
after_block_stage
after_block_staged_record
before_registry_stage
after_registry_stage
after_registry_staged_record
before_publish
during_header_rename
after_header_publish
during_block_rename
after_block_publish
after_snapshot_publish
before_index_stage
after_index_stage
after_publish
before_fsync
after_fsync
before_commit
after_commit
before_head_update
after_head_update
before_dir_sync
after_dir_sync
```

For each failpoint:

- opened a fresh store
- armed the failpoint
- attempted one block append
- closed the partial backend
- ran `recover_store()`
- verified recovered height ∈ {0, 1}
- verified the next append succeeds

Result: 28/28 failpoints passed.

## 2. Multi-block crash testing

- Built a chain of 100 blocks cleanly and recovered it successfully.
- Ran 5 deterministic randomized seeds:
  - target height 20
  - random failpoint among `{before_begin, after_publish, before_head_update, after_head_update, None}`
  - recovered after each append attempt
  - verified recovered height ≤ attempted height
  - verified continuation appends work

Result: all seeds passed.

## 3. Repeated recovery

Recovery is deterministic because:

- `recover_store()` is pure (no mutable state).
- It reads only canonical files, journal, and HEAD.
- It never trusts HEAD alone.
- It rebuilds indexes from canonical blocks.

Tests in `test_storage_recovery.py` assert identical recovered state.

## 4. Journal adversarial testing

| Attack | Behavior |
|---|---|
| Truncated final record | decode stops at first invalid record; earlier commits still valid |
| Corrupted checksum | same as above; corrupt trailing record ignored |
| Duplicate sequence number | Currently accepted if checksum valid; improvement noted below |
| Decreasing sequence | Same |
| Unknown record type | Ignored if parseable; no consensus action |
| Oversized record | Length bound rejects |
| COMMIT without BEGIN | COMMIT height still caps safe height; must match durable files |
| Multiple BEGIN | No special handling; only COMMIT matters for recovery height |
| BEGIN without COMMIT | safe_height falls back to zero or earlier COMMIT |

Classified: most issues are handled by the backward walk over canonical
files; journal is advisory for height bound only.

## 5. HEAD attacks

| Attack | Behavior |
|---|---|
| Missing HEAD | recovery falls back to journal commits or zero |
| Empty HEAD | decode error; treated as missing |
| Truncated HEAD | decode error; treated as missing |
| Malformed version | decode error; treated as missing |
| Wrong network ID | `RecoveryError` |
| Wrong genesis hash | `RecoveryError` |
| Height ahead of journal | rolled back to min(HEAD, last_commit) |
| Height behind journal | rolled forward by canonical files to last_commit |
| Wrong tip hash | rolled back until hash matches or reaches genesis |
| Trailing garbage | decode rejects |
| Stale HEAD | overwritten after verification |

## 6. Canonical file corruption

| Attack | Behavior |
|---|---|
| 148-byte header | rejected, rollback |
| 150-byte header | rejected, rollback |
| Bit-flipped header | hash mismatch, rollback |
| Block truncation | decode error, rollback |
| Block appended garbage | size mismatch, rollback |
| Block checksum corruption | decode error, rollback |
| Block/header disagreement | hash mismatch, rollback |
| Missing intermediate block | rollback to last continuous valid height |
| Swapped block files | prev_hash mismatch, rollback |

## 7. Snapshot attacks

- Wrong snapshot height, registry root, genesis, network: detected via meta
  file mismatch.
- Corrupted body: detected by state_hash meta check.
- Stale/future snapshot: recovery deletes snapshots above safe_height.
- Inconsistent with replay: snapshots are accelerators only; recovery uses
  canonical chain, so replay truth always wins.

## 8. Index attacks

- Missing index: rebuilt from canonical blocks.
- Wrong mapping: rebuilt from canonical blocks.
- Truncated/garbage: rebuilt from canonical blocks.
- Indexes never redefine canonical state.

## 9. Archive object attacks

- Bit-flipped bytes: hash mismatch on read.
- Partial file: hash mismatch.
- Wrong content-addressed path: mismatch or not found.
- Duplicate content insertion: idempotent.
- Manifest/content mismatch: hash check rejects.
- Missing referenced object: `StorageIOError`.

## 10. Single-writer lock

- Second backend in same process: `StorageIOError`.
- Lock released on close: re-acquisition succeeds.
- Stale lock with non-existent PID: lock acquired after stale detection.

Cross-process lock tests are planned for CI environments where subprocess
startup is reliable.

## 11. Cross-platform notes

- POSIX: directory fsync attempted.
- Windows: directory fsync is skipped because Windows has no portable
  directory-sync primitive.
- Atomic rename: `os.replace` on both platforms; same-directory replacement
  is expected to be atomic.

## 12. Storage Format V1 golden vectors

Created `storage-vectors/` with positive and negative examples:

- `HEAD`
- `0000000001.hdr`
- `0000000001.bin`
- `journal_begin_record.bin`
- `journal_commit_record.bin`
- corrupted variants

## 13. Performance baseline

- 100 appends: measured in `test_storage_performance.py` (slow test)
- Recovery of 100 blocks: measured in the same test

Numbers depend on the CI runner disk; recorded per-run in test output.

## 14. Verification

- `ruff check chainbreaker tests scripts` — passing
- `mypy chainbreaker` — passing
- `python test-vectors/validate_vectors.py` — no failures
- Storage test suite — 53 passed
- Full `pytest tests/` — 771 passed, 2 skipped (local)
- CI `CI` and `Rust Verifier CI` — green

## 15. Discovered defects / fixes

| Issue | Fix |
|---|---|
| `test_registry_state.py` subprocess test lacked `PYTHONPATH` on Windows | Set `PYTHONPATH` to repo root |
| Recovery only verified tip, not contiguous chain | Rewrote recovery to walk backward and verify prev_hash linkage |
| Sparse failpoints in commit path | Added 28 named failpoints |

## 16. Unresolved risks

- Journal sequence duplicates/decreases are not yet explicitly rejected.
- Cross-process lock and crash tests are marked for CI.
- Archive manifest/index integration with witness/attestation not yet wired.
- Delta snapshots not implemented.
- Pruning policy not implemented.
