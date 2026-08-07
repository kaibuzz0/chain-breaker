# Storage Crash Recovery Specification

Version: `chainbreaker-scripture-v2`  
Status: **Phase 7A design — no implementation yet**

This document is the operational crash-recovery companion to
`docs/PHASE7_STORAGE_ARCHITECTURE.md`. It gives a precise state machine for
recovering durable state after an unclean shutdown.

---

## 1. Core invariant

After recovery completes:

```text
HEAD <= highest_fully_durable_committed_block
```

`HEAD` must never point to a state that is only partially durable. A block is
fully durable only after all of its artifacts are flushed, the `COMMIT` record
is durable, and `HEAD` itself is durable.

---

## 2. Recovery inputs

Recovery reads the following durable structures from the configured `CHAIN_ROOT`:

1. `HEAD` — atomic tip pointer: `(height, block_hash)`.
2. `journal` — write-ahead log of commit attempts.
3. `headers/` — canonical 149-byte Header V2 files.
4. `blocks/` — canonical block record files.
5. `registry/snapshots/` — full registry-state snapshots.
6. `indexes/` — derived lookup tables.
7. `tmp/` — staging directory for incomplete writes.

---

## 3. Recovery procedure

### 3.1 Step 1 — Load HEAD

Read `HEAD`. If the file is missing, malformed, or its `block_hash` does not
match the header at the claimed height, treat the durable tip as genesis
(height 0).

### 3.2 Step 2 — Scan journal backward

Starting from the end of `journal`, read records backward until a valid
`COMMIT` or `HEAD_UPDATED` record is found. Let `H_commit` be the height of
that record. If no valid record is found, `H_commit = 0`.

Partially written trailing records are detected by checksum or length mismatch
and are ignored.

### 3.3 Step 3 — Determine safe height

```text
H_safe = min(HEAD.height, H_commit)
```

This is the highest height that is guaranteed to be fully durable.

### 3.4 Step 4 — Verify artifacts at H_safe

For height `H_safe`, verify that:

- `headers/{H_safe:010d}.hdr` exists and is exactly 149 bytes.
- `blocks/{H_safe:010d}.bin` exists, is correctly framed, and its body checksum matches.
- The block's hash equals `HEAD.block_hash`.
- Any referenced registry snapshot exists and passes hash verification.
- All referenced archive objects exist and match their content hashes.

If verification fails, decrement `H_safe` and repeat. Never advance `H_safe`
without verification.

### 3.5 Step 5 — Roll back partial state

For every height `H > H_safe`:

- Delete `headers/{H:010d}.hdr` if present.
- Delete `blocks/{H:010d}.bin` if present.
- Delete any registry snapshot at height `H`.
- Delete any index entries for height `H`.
- Delete any staged files in `tmp/` associated with height `H`.

### 3.6 Step 6 — Reconcile HEAD

If `HEAD.height > H_safe`, atomically rewrite `HEAD` to `(H_safe, block_hash)`.
Append an `ABORT` record to the journal describing the roll-back.

### 3.7 Step 7 — Rebuild derived state

Rebuild indexes and any missing snapshots from the authoritative chain data at
heights `0..H_safe`. Derived data must never change consensus results.

### 3.8 Step 8 — Return to consensus

Return `(H_safe, block_hash)` to the consensus engine. The node may now resume
normal operation by accepting blocks at height `H_safe + 1`.

---

## 4. State machine by crash point

| Crash point | Observable state | Recovery result |
|-------------|------------------|-----------------|
| Before BEGIN | No journal record | H_safe unchanged. |
| After BEGIN | BEGIN record only | Discard BEGIN; H_safe unchanged. |
| During staging | BEGIN + partial tmp files | Discard tmp files; discard BEGIN. |
| After staging, before rename | BEGIN + complete tmp files | Verify hashes; publish or discard. |
| During rename | Old or new file exists per path | Verify hashes; choose durable version. |
| After rename, before COMMIT | New files + BEGIN | Verify; append COMMIT if valid. |
| After COMMIT, before HEAD | COMMIT durable, HEAD old | Update HEAD to COMMIT height. |
| During HEAD update | Old or new HEAD exists | Choose HEAD that points to verified durable state. |
| During journal append | Partial trailing record | Ignore partial record; use last valid record. |

---

## 5. Determinism proof sketch

Recovery is deterministic because:

1. `H_safe` is computed from durable records only.
2. Verification at `H_safe` uses immutable hash checks.
3. Rollback removes only heights > H_safe.
4. Derived state is rebuilt from authoritative data.
5. The algorithm contains no branches that depend on wall-clock time,
   randomness, or uninitialized state.

Therefore any two honest nodes that crash at the same logical commit point will
recover to the same durable tip.

---

## 6. Open questions

1. Should `HEAD` store a small checksum of its own contents to detect partial
   writes?
2. Should recovery keep a journal of roll-backs for operator diagnosis?
3. What is the exact policy when `HEAD` and `H_commit` diverge by more than one
   block (e.g., after manual file manipulation)?
