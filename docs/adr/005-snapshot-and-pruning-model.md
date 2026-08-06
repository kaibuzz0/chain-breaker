# ADR 005 — Snapshot and Pruning Model

## Status

Proposed — Phase 7A design.

## Context

Replaying the entire chain from genesis to validate the current registry state becomes slower as the chain grows. Snapshots speed up replay. Pruning reduces storage growth. Both must remain compatible with the frozen consensus rules.

## Decision

- Take periodic **full registry snapshots** at fixed block heights (default every 100 blocks).
- Store **transaction deltas** between snapshots so replay can resume from the latest snapshot.
- Allow operators to **prune archive objects and redundant witnesses** according to a retention policy.
- Never prune blocks or registry data required to validate consensus.

## Rationale

Snapshots make startup and validation fast. Deltas keep storage bounded. Pruning gives operators control over disk usage without breaking consensus.

## Alternatives considered

| Approach | Rejected because |
|----------|------------------|
| Snapshots only, no deltas | Would require storing a full snapshot every block. |
| Deltas only, no snapshots | Replay from genesis remains slow forever. |
| Pruning blocks below a height | Would make historical validation impossible. |

## Invariants

1. A snapshot at height H contains the exact registry state produced by applying blocks 1..H.
2. Deltas between snapshots are deterministic and reproducible.
3. Pruning never removes a block whose hash is referenced by a later block.
4. Pruning never removes an archive object referenced by an unrevoked attestation.

## Extension points

- Snapshot interval is configurable.
- Pruning policy is pluggable (age, count, manual).
- Snapshot compression can be backend-specific.

## Compatibility implications

- Snapshot format is a storage-layer concern, not a consensus concern.
- Old nodes can ignore new snapshot files and still validate from genesis.
