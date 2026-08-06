# Phase 7A — Storage Architecture Design

This document defines the storage subsystem for Chain-Breaker Protocol v2. It is a design-only milestone; no consensus code is modified.

## Scope

Design the persistent storage model that the single-node engine will use before networking arrives. The storage layer must remain compatible with the frozen Protocol v2 core.

## Goals

1. **Durability** — chain state survives process crashes and power loss.
2. **Atomicity** — updates are committed all-or-nothing.
3. **Recoverability** — startup can detect and recover from partial writes.
4. **Compatibility** — storage format changes must not alter consensus hashes.
5. **Extensibility** — backend abstraction allows future SQLite/remote backends.

## Non-goals

- Multi-node replication.
- Network-facing APIs.
- Distributed consensus.
- Performance optimization beyond coarse baselines.

## Storage entities

| Entity | Description | Persistence requirement |
|--------|-------------|---------------------------|
| Block store | Sequence of finalized blocks | Append-only after finalization |
| Header index | Height -> header hash lookup | Derived, but cached for speed |
| Registry state | Curator registry at each height | Derived from chain; may checkpoint |
| Archive store | Content-addressed external documents | Content-addressed, immutable |
| Witness store | Attestations per block | Optional; can be reconstructed |
| Configuration | Node settings, network id, paths | Small, mutable |

## Directory layout (default flat-file backend)

```text
CHAIN_ROOT/
  chain/
    blocks/
      0000000000.bin
      0000000001.bin
      ...
    headers/
      0000000000.json
      ...
    indexes/
      height_to_hash.json
      hash_to_file.json
  registry/
    snapshots/
      0000000100.state        # periodic registry snapshots
    deltas/
      0000000001-0000000100.bin # compressed transaction deltas
  archive/
    objects/                    # content-addressed zlib-compressed blobs
    manifests/                # manifest files
  witness/
    0000000001.json
  tmp/                        # atomic-write staging
  lock/                       # single-process lock file
```

## Atomicity model

1. All state-changing writes are staged in `tmp/`.
2. After successful fsync, files are renamed into place.
3. A `HEAD` file records the last fully committed block height.
4. On startup, if `HEAD` is newer than the files present, roll back to `HEAD`.

## Snapshot model

- Registry snapshots are taken every N blocks (default 100).
- A snapshot contains the full registry state at that height.
- Replay starts from the nearest snapshot and applies deltas.
- Snapshot interval is configurable; it affects replay speed, not consensus.

## Pruning model

- Old archive objects are never deleted by consensus rules.
- Operators may prune redundant witness records after a retention policy.
- Block bodies below a configurable retention height may be moved to cold storage.
- Pruning must never remove data required to validate a frozen block.

## Corruption recovery

1. On startup, verify the hash chain from genesis to `HEAD`.
2. If a block file fails validation, truncate at the last valid block.
3. Rebuild indexes from valid blocks.
4. Recompute registry state from the latest snapshot + deltas.
5. Log all recovery actions to `recovery.log`.

## Backend abstraction (future)

```python
class StorageBackend(ABC):
    def read_block(self, height: int) -> BlockV2: ...
    def write_block(self, height: int, block: BlockV2) -> None: ...
    def read_registry_snapshot(self, height: int) -> RegistryState: ...
    def write_registry_snapshot(self, height: int, state: RegistryState) -> None: ...
    def read_archive_manifest(self, manifest_hash: str) -> dict: ...
    def write_archive_manifest(self, manifest_hash: str, manifest: dict) -> None: ...
    def fsync(self) -> None: ...
```

The first implementation is `FlatFileBackend`. Later backends (SQLite, S3, etc.) implement the same ABC.

## Interface with frozen core

- Storage formats must preserve `BlockV2` and `RegistryState` semantics.
- Storage cannot change canonical serialization or hashing.
- Storage backends may add metadata files, but consensus validation ignores them.

## Open risks

1. Windows vs. POSIX fsync semantics may differ; needs cross-platform test.
2. Large archive objects may exceed memory; streaming is required.
3. Concurrent read/write during background snapshot generation needs locking.
4. Migration between backend formats needs a spec before implementation.
