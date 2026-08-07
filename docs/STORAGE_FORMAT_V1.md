# Storage Format V1 Specification

Version: `chainbreaker-storage-v1`  
Status: **Phase 7A design — no implementation yet**

This document defines the concrete on-disk format for the default flat-file
storage backend. It is independent of Protocol V2 and may evolve without changing
consensus rules.

---

## 1. Directory layout

```text
CHAIN_ROOT/
  HEAD                       # atomic tip pointer
  journal                    # write-ahead log
  config.json                # node metadata
  tmp/                       # staging directory
  headers/                   # 149-byte canonical Header V2 files
  blocks/                    # canonical block record files
  registry/
    snapshots/               # full registry-state snapshots
    deltas/                  # compact transaction deltas between snapshots
  archive/
    objects/                 # content-addressed raw document bytes
    manifests/               # canonical manifest files
    index/                   # derived archive indexes
  witness/                   # cached attestation records
  indexes/                   # derived chain indexes
```

## 2. HEAD file

Atomic pointer. Written as:

```text
{height:020d}:{block_hash}

example:
00000000000000000012:000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
```

Update rule: write to `HEAD.tmp`, fsync, rename to `HEAD`, fsync directory.

## 3. Journal file

Append-only log of typed records. See `docs/adr/006-write-ahead-journal.md` for
the full record format.

Rotation rule: when the journal exceeds 64 MiB, rotate to
`journal.{last_commit_height}` and start a new `journal`. Old journal segments
may be deleted after a snapshot confirms all referenced heights are recoverable.

## 4. Header files

```text
headers/{height:010d}.hdr
```

Exactly 149 bytes. No framing. Integrity verified by recomputing
`SHA-256d(header_bytes)`.

## 5. Block files

```text
blocks/{height:010d}.bin
```

Framed as defined in `docs/PHASE7_STORAGE_ARCHITECTURE.md` Section 3.2.

## 6. Registry snapshots

```text
registry/snapshots/{height:010d}.state
```

Canonical binary registry-state bytes. Companion `.meta` JSON file is derived.

## 7. Registry deltas

```text
registry/deltas/{from_height:010d}-{to_height:010d}.delta
```

Compact binary record of governance transactions per block between snapshots.
Exact encoding to be defined before implementation.

## 8. Archive objects

```text
archive/objects/{hash[0:2]}/{hash[2:4]}/{hash}
```

Raw document bytes. The content hash is `SHA-256(raw_bytes)`.

## 9. Archive manifests

```text
archive/manifests/{hash[0:2]}/{hash[2:4]}/{hash}.manifest
```

Canonical JSON manifest. Manifest hash is `SHA-256(canonical_json_bytes)`.

## 10. Indexes

```text
indexes/height_to_hash.json
indexes/hash_to_height.json
indexes/curator_history.json
archive/index/content_to_manifest.json
archive/index/manifest_to_block.json
```

All indexes are derived and rebuildable.

## 11. Versioning

Storage format version is recorded in `config.json`:

```json
{
  "storage_format_version": 1,
  "network_id": "chainbreaker-scripture-v2",
  "genesis_hash": "...",
  "backend": "flat-file"
}
```

A node must refuse to open a `CHAIN_ROOT` whose `storage_format_version` is
higher than the code supports.
