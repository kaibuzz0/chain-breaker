# ADR 009 — Atomic Canonical-Tip Switch

## Status

Proposed — Phase 7G design.

## Context

Switching canonical branches writes multiple derived files and updates the tip pointer. If the switch is interrupted, the node could have a new `HEAD` but stale indexes, or a stale `HEAD` but new canonical files. Recovery must converge to exactly one deterministic state.

## Decision

The canonical tip switch has two durable steps:

1. **Prepare:** ensure all connect-set blocks are fully durable (journal `COMMIT` + canonical files).
2. **Commit:** atomically overwrite the single `HEAD` file to point to the new tip.

All derived data (indexes, snapshots) is updated **after** `HEAD` is durable. If derived rebuild fails or is interrupted, recovery rebuilds it from canonical blocks on next startup.

## Rationale

Making `HEAD` the single commit point keeps recovery simple: whatever `HEAD` points to after recovery is the canonical tip. Derived data is always rebuildable.

## Consequences

- A brief window exists where `HEAD` is new but indexes are stale. Reads must either tolerate rebuild or block until rebuild completes.
- Recovery must delete derived data that is inconsistent with `HEAD` before rebuilding.
- The atomic replace of `HEAD` must use a platform-atomic primitive (`os.replace`).

## Invariants

1. Only one `HEAD` file exists in the chain root.
2. `HEAD` is updated only after all connect-set blocks are durable.
3. Derived data is rebuilt from canonical files after `HEAD` update.
4. Recovery treats `HEAD` as authoritative and rebuilds everything else.

## Relationship to other ADRs

- ADR 004 — storage backend boundary: the backend performs the atomic commit.
- ADR 006 — write-ahead journal: journal records make connect-set blocks durable.
- ADR 007 — accumulated-work fork choice: the outcome of work comparison triggers the switch.
