# ADR 005 — Snapshot and Pruning Model

## Status

Accepted — Phase 7A design.

## Context

Replaying the entire chain from genesis to validate the current registry state
becomes slower as the chain grows. Snapshots and deltas make startup fast while
keeping storage bounded. Pruning gives operators control over disk usage, but it
must not destroy the preservation mission.

## Decision

- Take periodic **full registry snapshots** at fixed block heights (default every
  100 blocks).
- Store **transaction deltas** between snapshots so replay can resume from the
  latest snapshot.
- Allow operators to **prune archive objects and redundant witnesses** according
  to a retention policy.
- Never prune blocks, headers, or registry data required to validate consensus.

## Rationale

Full snapshots make startup and validation fast. Deltas keep storage bounded.
Pruning is a local operator choice; the protocol itself never deletes canonical
chain data.

## Alternatives considered

| Approach | Rejected because |
|----------|------------------|
| Snapshots only, no deltas | Would require storing a full snapshot every block. |
| Deltas only, no snapshots | Replay from genesis remains slow forever. |
| Pruning blocks below a height | Would make historical validation impossible. |
| Pruning archive objects by default | Would silently weaken provenance guarantees. |

## Invariants

1. A snapshot at height H contains the exact registry state produced by applying
   blocks 1..H.
2. Deltas between snapshots are deterministic and reproducible.
3. Pruning never removes a block whose hash is referenced by a later block.
4. Pruning never removes an archive object referenced by an unrevoked attestation.
5. Pruning never removes the minimum set of snapshots required for recovery.
6. A node that advertises archival provenance must retain all blocks, manifests,
   and content needed to prove it.

## Snapshot format

A snapshot file contains exactly the canonical binary serialization of
`RegistryState` at height H:

```text
snapshots/{height:010d}.state
```

A companion `.meta` file (derived) records height, network ID, genesis hash,
registry root, and snapshot hash for verification.

## Delta format

Between snapshots, the storage layer may store a compact record of governance
transactions applied in each block. The exact binary encoding will be defined
before implementation; it must be deterministically reproducible from chain
history.

## Pruning policy

| Node class | May prune | Must retain |
|------------|-----------|-------------|
| Archival | nothing | everything |
| Pruned | old snapshots beyond recovery minimum, redundant witnesses, unreferenced archive objects per explicit policy | canonical chain, genesis, referenced manifests/content |

## Extension points

- Snapshot interval is configurable.
- Pruning policy is pluggable (age, count, manual).
- Snapshot compression can be backend-specific.

## Compatibility implications

- Snapshot and delta formats are storage-layer concerns, not consensus concerns.
- Old nodes can ignore new snapshot files and still validate from genesis.
- Pruning does not change what the protocol considers valid; it only changes what
  a local node retains.
