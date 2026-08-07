# ADR 004 — Storage Backend Boundary

## Status

Accepted — Phase 7A design.

## Context

Chain-Breaker currently persists state in ad-hoc JSON/flat files. Before
networking and multi-node operation, we need a stable storage boundary that:

1. Keeps consensus code independent of filesystem details.
2. Allows future backends (SQLite, remote object store) without changing validation.
3. Supports atomic durable commits and crash recovery.
4. Makes storage format versioning independent of protocol versioning.

## Decision

Introduce a `StorageBackend` abstract base class in a future
`chainbreaker.storage` module. The consensus engine calls `append_block`,
`read_block`, `read_header`, `get_tip`, and related methods. The initial
implementation remains flat-file based. Future backends implement the same ABC.

The storage layer must never:

- modify canonical block bytes or headers;
- alter consensus hashes or serialization;
- decide whether a block is valid;
- advance `HEAD` beyond fully durable state.

## Rationale

A clean backend boundary prevents storage concerns from leaking into validation
logic. It also makes testing easier: tests can use an in-memory backend without
touching the filesystem, and crash-recovery tests can use a fault-injecting
backend.

## Alternatives considered

| Approach | Rejected because |
|----------|------------------|
| Storage logic scattered across modules | Would couple consensus to filesystem details. |
| SQLite as the only backend | Adds a heavy dependency before the interface is proven. |
| Direct blockchain integration | Too early; networking is not yet designed. |

## Invariants

1. `StorageBackend` implementations must preserve canonical block bytes.
2. `StorageBackend` must not modify consensus hashes or serialization.
3. All writes must be atomic (stage + fsync/flush + rename).
4. `HEAD` must never advance beyond fully persisted state.
5. Derived data (indexes, snapshots) may be rebuilt from authoritative chain data.

## Interface (conceptual)

```python
class StorageBackend(ABC):
    @abstractmethod
    def append_block(self, block: BlockV2, previous_state: RegistryState) -> None:
        """Validate, stage, commit, and update HEAD atomically."""

    @abstractmethod
    def read_block(self, height: int) -> BlockV2:
        """Return the block at the given height."""

    @abstractmethod
    def read_header(self, height: int) -> bytes:
        """Return the exact 149-byte canonical Header V2."""

    @abstractmethod
    def get_tip(self) -> tuple[int, str]:
        """Return (height, block_hash) from HEAD."""

    @abstractmethod
    def write_snapshot(self, height: int, state: RegistryState) -> None:
        """Persist a full registry snapshot."""

    @abstractmethod
    def read_snapshot(self, height: int) -> RegistryState:
        """Load a registry snapshot; verify it against chain history."""

    @abstractmethod
    def put_archive_object(self, content_hash: str, data: bytes) -> None:
        """Persist raw archive content by content hash."""

    @abstractmethod
    def get_archive_object(self, content_hash: str) -> bytes:
        """Return raw archive content; fail if missing or hash mismatch."""

    @abstractmethod
    def rebuild_indexes(self) -> None:
        """Rebuild all derived indexes from authoritative data."""

    @abstractmethod
    def recover(self) -> tuple[int, str]:
        """Run crash recovery and return durable tip."""
```

## Extension points

- New backends implement the ABC.
- Migration tooling copies data between backends without re-validating.
- Snapshot frequency is configurable per backend.
- A fault-injecting backend can simulate crashes at each commit step.

## Compatibility implications

- Storage format version is independent of protocol version.
- A node may migrate storage backends without changing its consensus identity.
- Changing the `StorageBackend` interface requires a storage-format version bump,
  not a protocol version bump.
