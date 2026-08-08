# ADR 008 — Branch-Specific Registry State

## Status

Proposed — Phase 7G design.

## Context

Registry state in Protocol V2 is deterministic from chain history. When two branches diverge after a common ancestor, each branch has its own registry state. A node must derive each branch's state independently to validate `registry_root` commitments and to avoid state leakage.

## Decision

Registry state is computed in **scratch space** per branch:

```text
state_common = state_at(common_ancestor)
state_candidate = replay(state_common, connect_set)
state_current   = replay(state_common, disconnect_set)
```

No mutable canonical registry state exists during evaluation. Only after a candidate is promoted does the node discard the old derived state and adopt the new.

## Rationale

Isolating branch replay guarantees that:

1. orphaned transactions never leak into the candidate branch;
2. candidate validation cannot corrupt current canonical state;
3. multiple queued candidates can be evaluated safely.

## Consequences

- Memory usage increases during deep reorgs.
- Replay cost is bounded by `max_reorg_depth` policy and snapshot interval.
- The storage backend may need a `read_state_at(height)` helper that returns replayed or snapshot state without mutating node state.

## Invariants

1. `registry_root` in every candidate block must match the replayed state at that height.
2. State objects used during replay are not shared between branches.
3. Canonical registry state is updated only after `HEAD` switch is durable.

## Relationship to other ADRs

- ADR 005 — snapshot model: snapshots may accelerate `state_at(common_ancestor)`.
- ADR 006 — journal: journal records describe which blocks are durable but do not define state.
