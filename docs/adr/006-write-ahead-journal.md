# ADR 006 — Write-Ahead Journal

## Status

Accepted — Phase 7A design.

## Context

Appending a block requires writing multiple files (header, block, snapshot,
indexes, archive references) and updating the tip pointer. Without a journal, a
crash in the middle of this sequence could leave the node in an inconsistent
state that is hard to recover from deterministically.

## Decision

Use a write-ahead journal to record multi-file commits. The journal is an
append-only log of typed records. Recovery scans the journal to determine the
highest fully committed height and rolls back any incomplete transaction.

## Journal record format

```text
record:
  magic        4 bytes   0x43 0x42 0x4A 0x52  "CBJR"
  type         1 byte    record type
  seq          8 bytes   uint64 LE, monotonically increasing
  height       8 bytes   uint64 LE
  payload_len  4 bytes   uint32 LE
  payload      payload_len bytes
  checksum     32 bytes  SHA-256d(type + seq + height + payload)
```

## Record types

| Type | Byte | Meaning |
|------|------|---------|
| `BEGIN` | 0x01 | Start a commit at height H. |
| `HEADER_STAGED` | 0x02 | Header file staged. |
| `BLOCK_STAGED` | 0x03 | Block file staged. |
| `REGISTRY_STAGED` | 0x04 | Registry snapshot staged. |
| `INDEX_STAGED` | 0x05 | Index file staged. |
| `ARCHIVE_REF` | 0x06 | Archive object references. |
| `COMMIT` | 0x10 | Transaction complete at height H. |
| `HEAD_UPDATED` | 0x11 | HEAD pointer updated. |
| `ABORT` | 0xFF | Transaction explicitly rolled back. |

## Commit protocol

1. Validate block and derive resulting state.
2. Write `BEGIN H` to journal and flush.
3. Stage all artifacts in `tmp/` and fsync.
4. Verify staged hashes.
5. Atomically publish artifacts with filesystem rename.
6. Fsync parent directories.
7. Append `COMMIT H` to journal and flush.
8. Atomically update HEAD to `(H, block_hash)`.
9. Fsync HEAD and its parent directory.

A block is fully durable only after step 9.

## Recovery rule

```text
H_max = min(last_COMPLETE_COMMIT_height, HEAD_height)
```

Recovery deletes any files at heights > H_max, verifies artifacts at H_max,
and rewrites HEAD if it pointed higher. An `ABORT` record is appended for any
rolled-back transaction.

## Invariants

1. `seq` never decreases.
2. A `BEGIN` without a matching `COMMIT` is incomplete.
3. A `COMMIT` without all referenced artifacts present is invalid.
4. `HEAD_UPDATED` is informational; the atomic HEAD file is authoritative.
5. Partially written records are ignored (detected by checksum/length).

## Extension points

- Journal rotation at fixed heights.
- Compression of historical journal segments.
- Alternative journal backends (single SQLite table, remote log) via the
  `StorageBackend` boundary.

## Compatibility implications

- The journal format is a storage-layer concern.
- A node may delete old journal segments after confirming all referenced heights
  are stable and snapshots exist.
- Recovery must be deterministic across backends that implement the same
  protocol.
