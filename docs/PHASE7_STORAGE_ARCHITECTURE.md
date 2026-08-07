# Phase 7A — Durable Storage Architecture

Version: `chainbreaker-scripture-v2`  
Status: **design-only milestone — no implementation code yet**

This document defines the durable storage subsystem for Chain-Breaker Protocol
v2. It is a design specification intended to be reviewed adversarially before any
persistence implementation begins.

---

## 1. Storage invariants

The storage layer exists to preserve consensus state across process restarts and
crashes. It does not define, modify, or relax any consensus rule.

### 1.1 Fundamental invariant

After recovery:

```text
HEAD <= highest_fully_durable_committed_block
```

`HEAD` is a storage-layer pointer. It must never identify a block whose canonical
bytes, derived state, or referenced artifacts are only partially durable. A block
becomes *fully durable* only when every artifact required to reconstruct it and
its consensus-valid state has been flushed to stable storage and the final commit
record has been written.

### 1.2 Truth hierarchy

```text
chain history  ==  consensus truth     (authoritative, immutable)
snapshots       ==  accelerator          (derived, rebuildable)
indexes         ==  accelerator          (derived, rebuildable)
caches          ==  performance layer    (derived, discardable)
```

Corruption or loss of any derived data must not change consensus results. Any
honest node must be able to re-derive the current state by replaying the chain
from genesis.

### 1.3 Deterministic replay

The canonical chain bytes are the only data the storage layer must protect
perfectly. Given the chain history and genesis constants, every registry state,
registry root, and attestation validity result is a pure deterministic function.

---

## 2. Authoritative disk formats

### 2.1 Required persisted forms

| Entity | Authoritative form | Notes |
|--------|-------------------|-------|
| Block headers | 149-byte canonical binary header (`*.hdr`) | Exact frozen Header V2 bytes. JSON may exist only as derived debug data. |
| Blocks | Canonical block record (`*.bin`) | Contains header + transaction list in a defined framing. |
| Registry snapshots | Canonical binary registry state (`*.state`) | Full deterministic serialization at a specific height. |
| Indexes | Derived lookup tables (`*.idx` / `*.json`) | Rebuildable from chain history. |
| Archive manifests | Canonical JSON manifest (`*.manifest`) | Bound to content hash and chain commitment. |
| Archive content | Raw content bytes (`objects/<hash>`) | Content-addressed, immutable. |
| Witnesses/attestations | Canonical attestation records (`*.witness`) | Reconstructible from blocks; may be cached. |
| Metadata | Node configuration (`config.json`) | Network ID, paths, backend type. Not consensus. |
| HEAD/tip record | Atomic pointer file (`HEAD`) | Single height + block hash. |
| Journal | Write-ahead log (`journal`) | Crash-recovery record. |

### 2.2 Header V2 authoritative representation

The frozen 149-byte canonical binary header is the authoritative persisted form.

```text
headers/0000000000.hdr   # 149 bytes, canonical
headers/0000000000.json  # optional derived/debug representation only
```

Consensus code never reads the JSON representation. Tools may generate JSON for
human inspection, but validation, hashing, and PoW always operate on the 149-byte
binary form.

---

## 3. Block storage

### 3.1 File naming

```text
blocks/0000000001.bin
blocks/0000000002.bin
...
blocks/{height:010d}.bin
headers/{height:010d}.hdr
```

Zero-padded 10-digit height supports chains up to 10^10 blocks without lexical
sorting ambiguity.

### 3.2 Block record format (`.bin`)

A block record stores the canonical block data needed for replay and validation.

```text
magic           4 bytes   0x43 0x42 0x42 0x32  "CBB2"
version         4 bytes   uint32 LE, value = 2
header_len      4 bytes   uint32 LE, always 149
header          149 bytes canonical Header V2
reserved        1 byte    0x00
body_len        8 bytes   uint64 LE
tx_count        4 bytes   uint32 LE
transactions    body_len bytes  canonical JSON array, UTF-8, sort_keys=True, no whitespace
body_checksum   32 bytes  SHA-256d(body_len + tx_count + transactions)
trailing        4 bytes   0x00 0x00 0x00 0x00
```

The checksum covers only the body so that corruption detection can distinguish
header corruption from transaction-body corruption.

### 3.3 Header file format (`.hdr`)

Exactly the 149-byte canonical Header V2. No framing, no checksum inside the
file; integrity is verified by recomputing `SHA-256d(header_bytes)` and comparing
against the header's own hash field when needed.

### 3.4 Maximum sizes

| Limit | Value | Rationale |
|-------|-------|-----------|
| Header size | 149 bytes | Frozen by Protocol V2. |
| Block body | 4 MiB | Prevents unbounded transaction payloads in a single block. |
| Transactions per block | 10,000 | Keeps Merkle-tree depth bounded. |
| Total block file | ~4 MiB + 200 bytes | Fits comfortably in memory during validation. |

### 3.5 Truncation and trailing bytes

- A file shorter than its declared length is rejected as truncated.
- A file longer than its declared length with non-zero trailing bytes is rejected.
- If the declared `body_len` + framing does not match the actual file size, the
  block is treated as corrupted and recovery rolls back past it.

---

## 4. Write-ahead journal

### 4.1 Purpose

The journal records multi-file commits atomically. A crash at any point leaves the
node able to determine whether a block was fully committed and, if not, to discard
partial artifacts.

### 4.2 Journal record format

Records are length-prefixed, checksummed, and independent.

```text
record:
  magic      4 bytes   0x43 0x42 0x4A 0x52  "CBJR"
  type       1 byte     record type
  seq        8 bytes   uint64 LE, monotonically increasing
  height     8 bytes   uint64 LE
  payload_len  4 bytes uint32 LE
  payload    payload_len bytes
  checksum   32 bytes  SHA-256d(type + seq + height + payload)
```

### 4.3 Record types

| Type | Byte | Payload |
|------|------|---------|
| `BEGIN` | 0x01 | `{height, target_hash, timestamp}` |
| `HEADER_STAGED` | 0x02 | `{height, header_path, header_hash}` |
| `BLOCK_STAGED` | 0x03 | `{height, block_path, block_hash}` |
| `REGISTRY_STAGED` | 0x04 | `{height, snapshot_path, snapshot_hash}` |
| `INDEX_STAGED` | 0x05 | `{height, index_path, index_hash}` |
| `ARCHIVE_REF` | 0x06 | `{height, archive_object_hashes: list}` |
| `COMMIT` | 0x10 | `{height, final_block_hash, new_registry_root}` |
| `HEAD_UPDATED` | 0x11 | `{height, block_hash}` |
| `ABORT` | 0xFF | `{height, reason}` |

### 4.4 Journal semantics

- `seq` is global per journal file and never decreases.
- A `BEGIN` without a matching `COMMIT` is incomplete and must be rolled back.
- A `COMMIT` without all referenced artifacts present is invalid; recovery
  treats it as an incomplete transaction and rolls back.
- `HEAD_UPDATED` is informational only; the atomic HEAD file is the real tip
  pointer.
- `ABORT` explicitly cancels a transaction and must be followed by cleanup.

### 4.5 Incomplete records

A partially written record (short magic, short length, or checksum mismatch) is
ignored. Recovery scans backward from the end of the journal to find the last valid
record.

### 4.6 Maximum record length

`payload_len` is limited to 64 MiB. Any record claiming a larger payload is rejected.

---

## 5. Atomic commit sequence

The canonical commit protocol for appending a new block at height `H`:

1. **Validate** the incoming block against Protocol V2 rules.
2. **Derive** the resulting consensus state:
   - `registry_root_after = registry_root(state_before_with_transactions_applied)`
3. **Write `BEGIN H`** to the journal and flush the journal.
4. **Stage artifacts** in `tmp/`:
   - `headers/H.hdr`
   - `blocks/H.bin`
   - `registry/snapshots/H.state` (if snapshot interval reached)
   - updated index files
5. **Flush/fsync** all staged files.
6. **Verify staged hashes** against expected values.
7. **Atomically publish** artifacts with filesystem renames (`tmp/X` → `chain/X`).
8. **Fsync parent directories** where required by the OS/filesystem.
9. **Append `COMMIT H`** to the journal and flush the journal.
10. **Atomically update HEAD** to point to `(H, block_hash)`.
11. **Fsync HEAD and its parent directory.**

### 5.1 Final authoritative marker

The **HEAD file** is the final authoritative commit marker. `COMMIT` exists so
recovery can reconstruct what was intended; HEAD exists so readers have a single,
stable tip pointer. Updating HEAD before fsyncing it is safe because recovery will
treat an unfynced HEAD as absent and replay from the previous durable tip.

A block is considered fully durable only after step 11 completes successfully. If
the process crashes before step 11, recovery must not advance HEAD past the
previous durable block.

---

## 6. Crash recovery state machine

Recovery scans the journal and filesystem state. It must converge to exactly one
deterministic result.

| Crash point | Recovery action |
|-------------|-----------------|
| Before `BEGIN` | Nothing to recover. HEAD unchanged. |
| After `BEGIN`, before staging | Discard `BEGIN`. HEAD unchanged. |
| During block/header write to `tmp/` | Truncate or delete incomplete staged files. Roll back `BEGIN`. |
| During registry snapshot/index write to `tmp/` | Same as above: discard partial staged files. |
| After staging, before rename | Verify staged hashes. If all match, proceed to publish. If any mismatch, discard and roll back. |
| During rename publication | Filesystem rename is atomic on POSIX and modern Windows NTFS. On crash, either old or new file exists; verify hashes to decide. |
| After publication, before `COMMIT` | Published files are valid but transaction not marked complete. Verify all artifacts, then append `COMMIT`. |
| After `COMMIT`, before HEAD update | Replay or trust `COMMIT`; atomically update HEAD to `H`. |
| During HEAD replacement | HEAD update uses atomic temp+rename. Either old or new HEAD exists. If new HEAD points to fully durable block, keep it. Otherwise revert. |
| During journal append | Last record may be partial; scan backward to last valid record. |

### 6.1 Recovery algorithm

1. Read current `HEAD`. If `HEAD` is missing or corrupt, treat tip as genesis.
2. Scan journal backward from end to find the last complete `COMMIT` or `HEAD_UPDATED`.
3. Let `H_commit` be the height of the last `COMMIT`.
4. Let `H_head` be the height in the HEAD file.
5. Set `H_max = min(H_commit, H_head)`.
6. For every height `H > H_max`, delete any partial or extra files.
7. Verify every artifact referenced by the last complete commit at `H_max`.
8. If verification fails, decrement `H_max` and repeat.
9. Rewrite `HEAD` to `H_max` if it pointed higher.
10. Append an `ABORT` record for any rolled-back heights.

---

## 7. Registry snapshots

### 7.1 Snapshot format

A snapshot is a complete canonical serialization of `RegistryState` at height `H`.

```text
snapshots/{height:010d}.state
```

The content is exactly the byte sequence produced by
`chainbreaker.registry_state.serialize_registry_state(state)`.

### 7.2 Snapshot metadata

A companion `.meta` file (derived, optional) records:

```json
{
  "height": 1234,
  "network_id": "chainbreaker-scripture-v2",
  "genesis_hash": "...",
  "registry_root": "...",
  "snapshot_hash": "...",
  "format_version": 1
}
```

`snapshot_hash` is `SHA-256(state_bytes)`.

### 7.3 Snapshot interval

Default: every 100 blocks. The interval is storage-tuning, not consensus.

### 7.4 Snapshot validity

A snapshot is accepted only if:

- its height matches a committed block,
- its `genesis_hash` matches the chain's genesis,
- its `registry_root` equals `registry_root(state)`, and
- replaying from the previous snapshot plus deltas reproduces it.

A corrupted snapshot is rejected and rebuilt from chain history.

---

## 8. Pruning policy

### 8.1 Node classes

| Class | Preserves | Use case |
|-------|-----------|----------|
| Archival node | Everything: all blocks, headers, snapshots, manifests, content, witnesses | Full historical provenance and auditability. |
| Pruned node | Recent blocks + selected archive objects | Disk-constrained operator. |

### 8.2 What may be pruned

- Archive objects no longer referenced by any attestation and explicitly marked
  for deletion by operator policy.
- Redundant witness files that can be reconstructed from blocks.
- Old index files (always rebuildable).
- Old registry snapshots beyond the minimum needed for recovery.

### 8.3 What must never be pruned

- Any block in the canonical chain.
- Any block header.
- Genesis state or genesis constants.
- Any archive object referenced by an unrevoked attestation.
- Any data required to validate a claim the node type advertises supporting.

### 8.4 Preservation mission guard

Pruning must not silently weaken historical verification guarantees. A node that
claims to preserve archival provenance must retain the chain, manifests, and
content needed to prove it.

---

## 9. Archive content store

### 9.1 Content-addressed layout

```text
archive/
  objects/
    ab/
      cd/
        abcd...ef01   # raw document bytes
  manifests/
    ab/
      cd/
        abcd...ef01.manifest   # canonical manifest JSON
  index/
    content_to_manifest.json    # derived
    manifest_to_block.json      # derived
```

Content hash = `SHA-256(raw_bytes)`.

### 9.2 Manifest

```json
{
  "content_hash": "abcd...",
  "size": 12345,
  "media_type": "application/pdf",
  "title": "...",
  "network_id": "chainbreaker-scripture-v2",
  "block_height": 42,
  "block_hash": "..."
}
```

Manifest hash = `SHA-256(canonical_json_bytes)`.

### 9.3 Insertion rules

1. Verify `SHA-256(content) == content_hash` before writing.
2. Reject duplicate insertions silently (idempotent).
3. Write content to `tmp/`, fsync, rename into `objects/`.
4. Write manifest to `tmp/`, fsync, rename into `manifests/`.
5. Update derived indexes only after both files are durable.

### 9.4 Missing or mismatched objects

- Missing referenced content causes validation failure, not silent acceptance.
- Manifest/content hash mismatch rejects the manifest.
- A node may mark a manifest as "content unavailable" if the object was pruned,
  but it must not claim the manifest is valid.

---

## 10. Indexes

### 10.1 Derived-only status

Indexes are pure derived state. They may be deleted and rebuilt without changing
consensus results.

### 10.2 Required indexes

| Index | Purpose | Rebuildable from |
|-------|---------|------------------|
| `height_to_block_hash` | Height → block hash | Block headers |
| `block_hash_to_height` | Block hash → height | Block headers |
| `curator_history` | Curator ID → record history | Registry snapshots + deltas |
| `archive_content_to_manifest` | Content hash → manifest | Archive store |
| `snapshot_lookup` | Height → snapshot path | Registry snapshots |

### 10.3 Corruption handling

A corrupt index is detected by hash/structure checks and rebuilt from the
authoritative chain data. Validation never trusts an index as authoritative.

---

## 11. Storage backend boundary

### 11.1 Abstract interface

A future `StorageBackend` ABC defines the boundary. Conceptual methods:

```python
class StorageBackend(ABC):
    def append_block(self, block: BlockV2, state: RegistryState) -> None: ...
    def read_block(self, height: int) -> BlockV2: ...
    def read_header(self, height: int) -> bytes: ...
    def get_tip(self) -> tuple[int, str]: ...
    def write_snapshot(self, height: int, state: RegistryState) -> None: ...
    def read_snapshot(self, height: int) -> RegistryState: ...
    def put_archive_object(self, content_hash: str, data: bytes) -> None: ...
    def get_archive_object(self, content_hash: str) -> bytes: ...
    def rebuild_indexes(self) -> None: ...
    def recover(self) -> tuple[int, str]: ...
```

### 11.2 Boundary rule

The storage layer **consumes** consensus results. It does not decide consensus
validity, alter canonical bytes, or change hashes.

---

## 12. Cross-platform durability

### 12.1 POSIX (Linux / macOS)

- Use `os.fsync(fd)` after writing file data.
- Use `os.fsync(dir_fd)` after `os.replace()` to ensure directory entries are durable.
- Atomic rename via `os.replace()`.

### 12.2 Windows

- Use `msvcrt.get_osfhandle` + `FlushFileBuffers` after writes.
- Directory durability is filesystem-dependent; NTFS generally journals metadata.
- Use `os.replace()` for atomic rename on NTFS.
- Symlinks and reparse points are rejected before file access (existing CLI rule).

### 12.3 Shared assumptions

- Power loss may occur at any point.
- Atomic rename means either old or new file is visible after recovery, never a
  partially written target.
- fsync/FlushFileBuffers does not guarantee against all hardware failures; it
  guarantees the OS/file-system cache is durable.

### 12.4 Path traversal

All storage paths are constructed from validated height integers and fixed
subdirectories. `..` and absolute paths in user input are rejected before any
storage operation.

---

## 13. Failure injection plan (future implementation)

A crash/fault suite will eventually terminate the process after every commit step:

- after `BEGIN`
- after each staged-file fsync
- after each rename
- after `COMMIT`
- during HEAD update

Additional fault injections:

- truncate `.bin`, `.hdr`, `.state`
- corrupt header bytes
- corrupt block body checksum
- corrupt journal record
- delete HEAD
- advance HEAD to a non-existent height
- delete a snapshot
- corrupt a snapshot
- corrupt an index
- leave an archive object partial

Recovery must produce either:

- the previous valid committed state, or
- the next fully committed valid state.

Never a hybrid or inconsistent state.

---

## 14. Storage security review

### 14.1 Threats and mitigations

| Threat | Mitigation |
|--------|------------|
| Local tampering | Hash verification on every read; derived data is rebuildable. |
| Malicious files | Strict length/magic/version checks; reject unexpected files. |
| Malformed lengths | Bounded length fields; reject records larger than max. |
| Disk exhaustion | Pre-allocate/stage in `tmp/`; fail before mutating canonical state. |
| Path traversal | Only fixed subdirectories and validated integer filenames. |
| Symlink/reparse attacks | Reject symlinks and reparse points before access. |
| Hash mismatch | Reject file; treat as missing; recover from prior state. |
| Rollback attacks | HEAD is the single tip pointer; journal records are sequential. |
| Stale snapshots | Snapshot metadata binds height, genesis hash, and registry root. |
| Partially written records | Journal records are checksummed; incomplete records are ignored. |

### 14.2 Separation of guarantees

- **Corruption detection** tells you data changed.
- **Crash consistency** ensures a crash leaves a valid prior or next state.
- **Malicious-operator resistance** ensures a local attacker cannot silently
  forge consensus-valid data without breaking hash puzzles or signatures.

They are not the same. This architecture provides all three at different layers.

---

## 15. Future networking compatibility

The storage design anticipates future networking without implementing it:

- Blocks can be imported into a **staging area** before becoming canonical.
- Validation runs on staged blocks; only valid blocks are committed.
- Alternate branches can be stored in `branches/<fork_hash>/` without affecting `HEAD`.
- Canonical tip switches atomically via HEAD update after full validation.
- Reorg logic will be added in a later phase and must obey the same commit protocol.

---

## 16. Unresolved questions

1. Should the journal be a single ever-growing file or rotated at fixed heights?
2. What is the exact binary encoding for registry-state deltas between snapshots?
3. Should archive objects be compressed by default? (Content-hash must cover
   uncompressed bytes if compression is transparent.)
4. How should a pruned node advertise which historical heights it can validate?
5. What is the rollback policy when an archive object referenced by an
   attestation is missing on a pruned node?

These questions will be answered before implementation begins.
