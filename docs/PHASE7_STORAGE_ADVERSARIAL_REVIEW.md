# Phase 7A Storage Adversarial Review

Version: `chainbreaker-scripture-v2`  
Status: **design-only review — no implementation yet**

This document attacks the Phase 7A durable-storage design before any code is
written. Findings are classified and the design is fixed in the accompanying
architecture documents.

---

## Review methodology

For each designed component we ask:

1. Can `HEAD` point past durable data?
2. Can a `COMMIT` exist while an artifact is absent?
3. Can recovery choose two different states?
4. Can a corrupted snapshot override replay?
5. Can a corrupt index change validation?
6. Can archive data be replaced without detection?
7. Can Windows/Linux durability semantics diverge dangerously?
8. Can concurrent writers corrupt canonical state?
9. Can a crash create a valid-looking partial block?
10. Can a local attacker roll the chain back undetectably?

---

## Findings

### 1. HEAD could point past durable data if updated before fsync — CRITICAL

**Attack:** process writes `HEAD.tmp`, renames to `HEAD`, then crashes before
fsync completes. On some filesystems the new `HEAD` might appear with partial or
stale contents.

**Design fix:** Recovery treats `HEAD` as suspect until its contents are
verified. The safe height is `min(HEAD.height, H_commit)`. HEAD is only accepted
if the header and block files at the claimed height exist and pass hash checks.
(See `docs/STORAGE_CRASH_RECOVERY.md` Section 3.3.)

### 2. COMMIT could exist while an artifact is absent — HIGH

**Attack:** journal `COMMIT` is flushed, but the block file rename failed or was
partially rolled back by the OS.

**Design fix:** Recovery always verifies every artifact referenced by the last
`COMMIT` before accepting its height. If any artifact is missing or corrupt,
`H_safe` is decremented until a fully verifiable height is found.
(See `docs/STORAGE_CRASH_RECOVERY.md` Section 3.4.)

### 3. Recovery could choose different states on different runs — HIGH

**Attack:** nondeterministic use of filesystem mtimes, unsorted directory listings,
or cached state.

**Design fix:** Recovery uses only the journal sequence numbers and HEAD contents.
The algorithm is deterministic: scan backward, take `min(HEAD, last COMMIT)`,
verify, roll back heights above. No filesystem ordering or timestamps are used for
decisions.

### 4. Corrupted snapshot could override replay — MEDIUM

**Attack:** a malicious operator replaces a `.state` file with arbitrary bytes.

**Design fix:** Snapshots are verified against `registry_root(state)` and the
chain height before use. A corrupt snapshot is rejected and rebuilt from chain
history. Snapshots are accelerators, not truth.
(See `docs/PHASE7_STORAGE_ARCHITECTURE.md` Section 7.4.)

### 5. Corrupt index could change validation — MEDIUM

**Attack:** `height_to_block_hash` index maps a height to a wrong block hash.

**Design fix:** Indexes are explicitly derived and rebuildable. Consensus code
never reads an index as authoritative. Any hash lookup can be verified by
reading the canonical header and recomputing its hash.
(See `docs/PHASE7_STORAGE_ARCHITECTURE.md` Section 10.)

### 6. Archive data could be replaced without detection — MEDIUM

**Attack:** an attacker swaps one archive object for another, keeping the same
filename hash by exploiting a SHA-256 collision or path manipulation.

**Design fix:** Content is stored at a path derived from its actual hash. On read,
`SHA-256(content)` is recomputed and compared to the requested hash. Manifests
also bind content hash and block commitment. A mismatch rejects the read.
(See `docs/PHASE7_STORAGE_ARCHITECTURE.md` Section 9.)

### 7. Windows/Linux durability semantics could diverge — MEDIUM

**Attack:** commit protocol assumes POSIX directory fsync, which has no direct
equivalent on all Windows filesystems.

**Design fix:** Cross-platform section explicitly documents that Windows uses
`FlushFileBuffers` and that directory durability depends on the filesystem. The
commit protocol still uses atomic temp+rename, which is supported on NTFS.
Recovery verification compensates for any residual ordering uncertainty.
(See `docs/PHASE7_STORAGE_ARCHITECTURE.md` Section 12.)

### 8. Concurrent writers could corrupt canonical state — HIGH

**Attack:** two processes call `append_block` simultaneously and interleave
writes.

**Design fix:** The storage design assumes a single writer per `CHAIN_ROOT`. A
`lock/` directory with a process-specific lock file will guard the writer. Future
phases may add explicit file locking or a single-node daemon model.
(See `docs/STORAGE_FORMAT_V1.md` Section 1.)

### 9. Crash could create a valid-looking partial block — LOW

**Attack:** a truncated `.bin` file passes length checks because the header is
complete but the body is partial.

**Design fix:** Block records include `body_len`, `tx_count`, and a `body_checksum`.
Truncation is detected by file-size mismatch and body checksum failure. Header-only
files are rejected.
(See `docs/PHASE7_STORAGE_ARCHITECTURE.md` Section 3.5.)

### 10. Local attacker could roll the chain back undetectably — LOW

**Attack:** attacker overwrites `HEAD` with an earlier height and deletes newer
files.

**Design fix:** This is a malicious-operator scenario, not a crash scenario. The
node detects the rollback because files referenced by `HEAD` must exist and pass
hash checks. Missing newer blocks are not silently accepted as canonical; the
node simply treats them as absent. A future networking phase will compare tips
with peers to detect rollback attacks.
(See `docs/PHASE7_STORAGE_ARCHITECTURE.md` Section 14.)

---

## Design changes made in response

1. Added explicit `H_safe = min(HEAD, last COMMIT)` rule.
2. Mandated verification of every artifact at `H_safe` before accepting it.
3. Required `ABORT` records after rollback.
4. Classified all derived data as rebuildable and non-authoritative.
5. Added content-hash verification on archive reads.
6. Documented cross-platform durability limits.
7. Added single-writer lock assumption.

---

## Unresolved risks

1. Exact single-writer locking mechanism not yet specified.
2. Journal rotation policy not finalized.
3. Registry delta binary encoding not finalized.
4. Behavior when a pruned node is asked to validate a missing archive object.
5. Performance bounds for recovery on very long chains not analyzed.

These will be resolved before implementation begins.
