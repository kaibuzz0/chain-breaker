# ADR 007 — Accumulated-Work Fork Choice

## Status

Proposed — Phase 7G design.

## Context

Protocol V2 defines valid blocks, valid registry state, and deterministic replay. It does not define how a node chooses between two competing valid histories. The choice rule is a node-local policy, but it must be deterministic and consistent across honest nodes or the network will partition.

Height alone is insecure: an adversary can mine many low-difficulty blocks quickly. Bitcoin-style accumulated proof-of-work is the standard defense.

## Decision

Chain-Breaker nodes select the canonical branch using **accumulated proof-of-work** from the common ancestor to each candidate tip.

```text
work(block)  = 2**256 // (block.target + 1)
work(branch) = sum(work(block) for block in branch)
```

A candidate branch is promoted only if:

```text
work(candidate) > work(current)
```

Equal work is a tie; the existing canonical branch retains authority.

## Rationale

Accumulated work directly measures the energy/computation committed to a branch. It is invariant under block count, height, and timestamp manipulation as long as the proof-of-work function is correctly evaluated.

## Consequences

- Nodes must compute or cache work per block.
- Reorgs require replaying and comparing branch work.
- Longer chains with lower total work are ignored.

## Invariants

1. `work` is computed from the actual `target` field in the header.
2. Work sums are exact integer arithmetic.
3. Equal-work candidates never cause a reorg.
4. Work comparison never short-circuits validation.

## Relationship to other ADRs

- ADR 002 — consensus freeze: this rule is a node policy, not a consensus rule change.
- ADR 008 — branch-specific state: replay produces the registry state used during work comparison.
- ADR 009 — atomic tip switch: work comparison outcome drives the atomic `HEAD` update.
