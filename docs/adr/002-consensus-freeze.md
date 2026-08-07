# ADR 002 — Consensus and Registry-Governance Freeze

## Status

Accepted — frozen at v2.0.0-alpha.

## Context

Before adding networking, storage backends, and distributed operation, the consensus rules and governance reducer must be stable. Networking exposes hidden consensus assumptions; a stable core prevents network code from forcing consensus changes.

## Decision

The following are frozen for Protocol v2:

1. Block validation rules.
2. Difficulty target interpretation and PoW validation.
3. Chain selection rule: longest valid chain.
4. Registry governance reducer transitions.
5. Curator action ordering and signature requirements.
6. Historical attestation validation.
7. Registry-root commitments per block.

## Rationale

Freezing consensus first means that networking and storage teams can build against a contract instead of a moving target. It also makes external review tractable: reviewers can focus on a fixed set of rules.

## Alternatives considered

| Approach | Rejected because |
|----------|------------------|
| Freeze later, after networking | Networking design would be coupled to unfinished consensus details. |
| Freeze everything including CLI | CLI presentation is allowed to evolve; command names and semantics are frozen, not help text. |
| Never freeze | Makes multi-client interoperability impossible. |

## Invariants that must never change

1. A valid block's hash satisfies the target.
2. A block's `registry_root` is the SHA-256 of the canonical serialized registry state *before* applying that block's actions; the post-block state is used for the next block's commitment.
3. Curator `register` requires a valid public key and self-signature.
4. Curator `rotate` requires the old key's signature and the new key.
5. Curator `revoke` permanently removes the curator from the active set.
6. Attestations are valid only from active curators at or before the attested block height.

## Extension points

- Reorg engine (Phase 9) may change chain selection behavior but must still honor the same validation rules.
- Multi-sig curator policies can be added as new action types under a future protocol version.

## Compatibility implications

- Any change to these invariants requires Protocol v3 or later.
- A v2 node must always accept a chain that was valid under v2 rules.
