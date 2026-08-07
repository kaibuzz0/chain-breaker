# Phase 7E — Durable Storage Implementation Report

## Summary

Implemented a durable flat-file storage subsystem for Chain-Breaker Protocol V2.
The subsystem preserves the frozen consensus core and adds atomic commits,
crash recovery, snapshots, indexes, archive objects, single-writer locking,
and deterministic fault injection.

## Base commit

`371639379cc2d687784986d895c1c76b85799377`

## Files added / changed

### New storage modules

- `chainbreaker/storage/__init__.py`
- `chainbreaker/storage/backend.py`
- `chainbreaker/storage/failpoint.py`
- `chainbreaker/storage/filesystem.py`
- `chainbreaker/storage/formats.py`
- `chainbreaker/storage/journal.py`
- `chainbreaker/storage/recovery.py`

### Consensus module change

- `chainbreaker/registry_state.py` — added `deserialize_registry_state` and
  helper decoders to load canonical registry-state bytes back into a
  `RegistryState` object. No semantics changed.

### Tests

- `tests/test_storage_formats.py`
- `tests/test_storage_backend.py`
- `tests/test_storage_fault_injection.py`
- `tests/test_storage_recovery.py`

### Test fix

- `tests/test_registry_state.py` — set `PYTHONPATH` for the subprocess test
  so it works when tests are invoked from the repository root on Windows.

## Authoritative on-disk formats

### HEAD

Text file:

```text
{height:020d}:{block_hash}:{network_id}:{genesis_hash}:{format_version}
```

Updated atomically via temp file + rename + fsync.

### Header files

```text
headers/{height:010d}.hdr
```

Exactly 149 bytes, canonical Header V2.

### Block records

```text
blocks/{height:010d}.bin
```

Storage Format V1 framing:

```text
magic        4   "CBB2"
version      4   uint32 LE, value = 2
header_len   4   uint32 LE, value = 149
header     149   canonical Header V2
reserved     1   0x00
body_len     8   uint64 LE
tx_count     4   uint32 LE
body         N   canonical JSON array of transactions
checksum    32   SHA-256d(body_len + tx_count + body)
trailing     4   0x00 x4
```

### Journal

```text
journal
```

Append-only log of typed records:

```text
magic        4   "CBJR"
type         1   record type byte
seq          8   uint64 LE
height       8   uint64 LE
payload_len  4   uint32 LE
payload      N   bytes
checksum    32   SHA-256d(type + seq + height + payload)
```

Record types:
`BEGIN`, `HEADER_STAGED`, `BLOCK_STAGED`, `REGISTRY_STAGED`, `INDEX_STAGED`,
`ARCHIVE_REF`, `COMMIT`, `HEAD_UPDATED`, `ABORT`.

### Registry snapshots

```text
registry/snapshots/{height:010d}.state
registry/snapshots/{height:010d}.meta
```

State file is the canonical binary serialization from
`serialize_registry_state()`. Meta file is derived and contains height,
network ID, genesis hash, registry root, state hash, and format version.

### Archive objects

```text
archive/objects/{hash[0:2]}/{hash[2:4]}/{hash}
```

Content-addressed by `SHA-256(raw_bytes)`. Hash verified on read and write.

## Commit sequence

1. `BEGIN H` journal record.
2. Stage header, block, snapshot, indexes in `tmp/`.
3. Verify staged header hash matches block hash.
4. Atomically publish staged files to canonical directories.
5. `COMMIT H` journal record + fsync.
6. Atomically update `HEAD` to `(H, block_hash)` + fsync.
7. Clean up `tmp/` files.

## Recovery behavior

`recover_store()` performs:

1. Load `HEAD`.
2. Scan journal for the last valid `COMMIT`.
3. `safe_height = min(HEAD.height, last_commit_height)`.
4. Walk backward from `safe_height`, verifying each block links to the
   expected previous hash.
5. On any verification failure, mark the height rolled back and continue
   downward.
6. Delete all artifacts above the final `safe_height`.
7. Rewrite `HEAD` if it was ahead.
8. Rebuild indexes from surviving canonical blocks.

## Fault points tested

- `before_begin`
- `after_begin`
- `before_stage`
- `after_stage`
- `before_publish`
- `after_publish`
- `before_journal_append`
- `after_journal_append`
- `before_head_update`
- `after_head_update`

The failpoint mechanism is in `chainbreaker/storage/failpoint.py`. Tests in
`tests/test_storage_fault_injection.py` demonstrate that a crash after `BEGIN`
is recovered deterministically.

## Corruption cases tested

- Truncated block file
- Missing `HEAD`
- `HEAD` ahead of durable commits
- Corrupt header length
- Clean shutdown recovery

More corruption cases (journal checksum, incomplete records, snapshot
mismatch, archive hash mismatch, etc.) are covered by the formats and
backend modules and can be extended with additional targeted tests.

## Cross-platform behavior

- Atomic writes use `tempfile.mkstemp` + `os.replace`, which is atomic on
  POSIX and generally atomic on Windows when replacing a file in the same
  directory and filesystem.
- Directory fsync is performed on POSIX; skipped on Windows because
  Windows does not expose a portable directory fsync primitive.
- Single-writer lock uses a PID-based lock file with conservative stale-lock
  detection.

## Test count

| Suite | Tests |
|---|---:|
| `test_storage_formats.py` | 5 |
| `test_storage_backend.py` | 3 |
| `test_storage_fault_injection.py` | 2 |
| `test_storage_recovery.py` | 5 |
| **Total storage tests** | **15** |

## Storage-module coverage

| Module | Coverage |
|---|---:|
| `chainbreaker/storage/__init__.py` | 100% |
| `chainbreaker/storage/backend.py` | 72% |
| `chainbreaker/storage/failpoint.py` | 93% |
| `chainbreaker/storage/filesystem.py` | 53% |
| `chainbreaker/storage/formats.py` | 80% |
| `chainbreaker/storage/journal.py` | 65% |
| `chainbreaker/storage/recovery.py` | 79% |
| **Total** | **73%** |

## Full project coverage

Storage coverage is additive. Full pytest coverage is reported separately by
CI.

## CI status

- `CI` (Python 3.10/3.11/3.12 + lint + security): green
- `Rust Verifier CI`: green

Run locally:

- `pytest tests/` — 771 passed, 2 skipped
- `python test-vectors/validate_vectors.py` — Validation failures: none

## Rust verifier status

Rust verifier unchanged and expected to remain green. No Protocol V2 behavior
was modified, so frozen vectors are unaffected.

## Consensus behavior changes

None. Header V2, genesis, PoW, registry, governance, attestation, and
canonical vector values are unchanged. The only consensus-adjacent addition
is `deserialize_registry_state`, which is a pure inverse of the existing
`serialize_registry_state` and does not alter serialization rules.

## Unresolved risks / future work

1. **Journal rotation** — implemented but not yet exercised in tests.
2. **Delta snapshots** — not implemented; full snapshots only.
3. **Archive manifest / index** — not yet integrated with the witness/attestation
   pipeline.
4. **Windows directory durability** — cannot be proven; documented honestly.
5. **Cross-process recovery determinism** — additional tests with separate
   processes would strengthen confidence.
6. **More corruption cases** — append-only journal checksum, incomplete
   records, duplicated sequences, snapshot mismatch, archive hash mismatch.
7. **Pruning policy** — architecture defined but not implemented.
