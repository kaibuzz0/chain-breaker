# Chain-Breaker System Architecture

This document is the master map of the Chain-Breaker project. It defines the layered structure, dependency rules, and extension points. Any future module must fit into one of these layers and obey the dependency arrows.

## Design philosophy

- **Consensus core is sacred.** Layers 1 and 2 are frozen at alpha. They change only for protocol version bumps or proven defects.
- **Outer layers adapt to the core, never the reverse.** CLI, storage, and networking are consumers of the consensus engine.
- **Layer boundaries are enforced by imports, not convention.** A layer may only import from itself or layers below it.

## Layer overview

| Layer | Name | Responsibility | Frozen at alpha |
|-------|------|--------------|-----------------|
| 1 | Consensus Engine | Block, header, PoW, chain validation, canonical serialization | yes |
| 2 | Registry Governance | Curator registry reducer, rotate/revoke rules, root commitments | yes |
| 3 | Archive Layer | Block storage, witness records, integrity verification | interface frozen, backends not |
| 4 | CLI | Operator interface, local workflow orchestration, input validation | command names frozen |
| 5 | Networking (future) | Peer protocol, gossip, sync, mempool | not implemented |
| 6 | Storage (future) | Backend abstraction, pruning, snapshots, replication | not implemented |
| 7 | Replication (future) | Archival replication, multi-node consistency, cluster operations | not implemented |

## Dependency rules

```text
Layer 7  Replication
    | depends on 6, 5, 4, 3, 2, 1
Layer 6  Storage
    | depends on 3, 2, 1
Layer 5  Networking
    | depends on 4, 3, 2, 1
Layer 4  CLI
    | depends on 3, 2, 1
Layer 3  Archive Layer
    | depends on 2, 1
Layer 2  Registry Governance
    | depends on 1
Layer 1  Consensus Engine
    | no upward dependencies
```

A layer must never import from a layer above it. Circular dependencies between sibling modules within a layer are also prohibited.

## Layer 1 — Consensus Engine

### Modules

- `chainbreaker.codec` — canonical serialization, hash pre-images, deterministic encoding.
- `chainbreaker.block` — Header v2, Block v2, genesis construction.
- `chainbreaker.consensus` — validation rules, difficulty, chain selection.

### Invariants

1. A block hash is `SHA-256(canonical(header))`.
2. Header field order is fixed for all time for Protocol v2.
3. Genesis block is deterministic given a seed registry and timestamp.
4. Proof-of-work target is a 256-bit threshold; a valid block satisfies `int(hash) < target`.

### Extension points

- Header version bumps require a new layer-1 module (e.g. `block_v3.py`) and a migration path.
- New hash algorithms require a new codec variant and explicit protocol version.

## Layer 2 — Registry Governance

### Modules

- `chainbreaker.registry_state` — Registry reducer, curator state, action validation.
- `chainbreaker.governance` — CLI glue and curator action construction.
- `chainbreaker.witness` — Attestation creation and verification.

### Invariants

1. The registry root after N blocks must equal the reducer applied to the genesis registry plus all N actions.
2. Curator actions are ordered: `register`, `rotate`, `revoke`.
3. A revoked curator cannot sign attestations after the revoking block.
4. A rotated key inherits historical attestations unless explicitly invalidated.

### Extension points

- New governance actions require ADR approval and a protocol version bump.
- Multi-sig curator policies belong here, not in layer 1.

## Layer 3 — Archive Layer

### Modules

- `chainbreaker.archive` — Block and witness persistence, atomic writes.
- `chainbreaker.cli_v2` (archive subcommands) — Operator-facing archive commands.

### Invariants

1. Archive files are append-only after finalization.
2. The archive records the registry root at every block boundary.
3. A corrupted archive file is detected before any dependent operation proceeds.

### Future work

- Pluggable backend interface (file, SQLite, remote object store).
- Compaction and pruning of redundant witness records.
- Snapshot generation at fixed block heights.

## Layer 4 — CLI

### Modules

- `chainbreaker.cli_v2` — Top-level operator commands.
- `chainbreaker.main` (future) — Entry point orchestration.

### Frozen contracts

- Command names: `chain`, `curator`, `block`, `archive`, `attest`, `verify`.
- Argument semantics for path, key, and force flags.
- Exit codes: `0` success, `1` user error, `2` system error, `3` validation/security failure.

### Security responsibilities

- Path traversal rejection.
- Symlink rejection before any read/write.
- Atomic writes to prevent half-written state.
- UTF-8 validation on free-form input.

## Layer 5 — Networking (future)

### Responsibilities

- Peer discovery and handshake.
- Block and transaction propagation.
- Synchronization protocol.
- Mempool for pending actions.

### Constraints

- All network messages must validate through Layer 1 and Layer 2 before acceptance.
- Network failures must not corrupt local chain state.
- Peer authentication is additive; it must not replace on-disk signature validation.

## Layer 6 — Storage (future)

### Responsibilities

- Backend abstraction (flat file, SQLite, etc.).
- Pruning and compaction.
- Migration tooling between storage versions.
- Indexing for fast registry-root lookups.

### Constraints

- Storage format changes must not alter consensus hashes.
- Backward compatibility must be maintained for at least one major version.

## Layer 7 — Replication (future)

### Responsibilities

- Multi-node archival replication.
- Cluster-level consensus health checks.
- Operator tooling for node federation.

## Cross-layer rules

| Allowed | Forbidden |
|---------|-----------|
| CLI imports Archive | CLI imports Networking |
| Archive imports Registry | Registry imports CLI |
| Registry imports Consensus | Consensus imports anything above Layer 1 |
| Networking imports CLI | Networking imports Storage directly |

## Change control

- Layers 1 and 2: require ADR and protocol version bump.
- Layer 3 interface: require ADR.
- Layer 4 command names: require compatibility note.
- Layers 5-7: follow existing layer rules and ADR for new subsystems.
