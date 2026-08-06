# ADR 004 — Storage Backend Boundary

## Status

Proposed — Phase 7A design.

## Context

Chain-Breaker currently stores all state in ad-hoc flat files. Before networking and multi-node operation, we need a stable storage boundary so that backends can be swapped without touching consensus code.

## Decision

Introduce a `StorageBackend` abstract base class in a new `chainbreaker.storage` module. The consensus engine reads and writes blocks, registry snapshots, and archive manifests only through this interface.

The initial implementation remains flat-file based. Future backends (SQLite, remote object store) implement the same ABC.

## Rationale

A clean backend boundary prevents storage concerns from leaking into validation logic. It also makes testing easier: tests can use an in-memory backend.

## Alternatives considered

| Approach | Rejected because |
|----------|------------------|
| Storage logic scattered across modules | Would couple consensus to filesystem details. |
| SQLite as the only backend | Adds a heavy dependency before the interface is proven. |
| Direct blockchain integration | Too early; networking is not yet designed. |

## Invariants

1. `StorageBackend` implementations must preserve canonical block bytes.
2. `StorageBackend` must not modify consensus hashes or serialization.
3. All writes must be atomic (stage + fsync + rename).
4. `HEAD` must never advance beyond fully persisted state.

## Extension points

- New backends implement the ABC.
- Migration tooling copies data between backends without re-validating.
- Snapshot frequency is configurable per backend.

## Compatibility implications

- Storage format version is independent of protocol version.
- A node may migrate storage backends without changing its consensus identity.
