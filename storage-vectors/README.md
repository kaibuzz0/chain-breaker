# Storage Format V1 Golden Vectors

These are example bytes for Chain-Breaker Storage Format V1. They are not
Protocol V2 consensus vectors; they describe the on-disk storage layer only.

## Files

- `HEAD` — example HEAD file
- `0000000001.hdr` — canonical 149-byte Header V2
- `0000000001.bin` — Storage Format V1 block record
- `journal_begin_record.bin` — typed BEGIN journal record
- `journal_commit_record.bin` — typed COMMIT journal record
- `0000000001_148byte.hdr` — truncated header (should be rejected)
- `0000000001_trailing.hdr` — header with trailing bytes (should be rejected)
- `0000000001_truncated.bin` — truncated block record (should be rejected)
- `0000000001_garbage.bin` — block record with trailing garbage (should be rejected)

## Verification

Use `chainbreaker/storage/formats.py` to decode these files. Each positive
example must round-trip exactly; each negative example must raise a
`ValueError` or `StorageIOError`.
