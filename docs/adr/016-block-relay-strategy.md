# ADR 016: Block Relay Strategy

## Status

**Proposed — Phase 8J**

## Context

Chain-Breaker nodes need a way to propagate newly validated blocks to peers.
Sync (Phase 8I) handles catch-up, but relay handles live propagation.

## Decision

Block relay in Protocol V1 will use an **inventory/request model**:

1. A node sends `INV_BLOCK` with block hashes to a subset of peers.
2. Interested peers respond with `GET_BLOCK`.
3. The announcer sends the full `BLOCK`.
4. The receiver validates and then repeats the announcement cycle.

Key design choices:

- **Pull model**, not push. Full blocks are never unsolicited.
- **Small announcements**; large data is requested on demand.
- **No new wire message types** required; reuse `INV_BLOCK`/`GET_BLOCK`/`BLOCK`.
- **Validation before relay** is mandatory.
- **Orphan pool is bounded and private.** Orphans are not relayed.
- **Relay remains separate from sync.** Sync catches up; relay propagates
  the tip.

## Consequences

- Bandwidth is conserved by avoiding blind broadcast of full blocks.
- Duplicate suppression and rate limits prevent amplification attacks.
- Slightly higher latency than naive broadcast, but much better DoS
  resistance.
- Orphan handling adds complexity but is bounded by strict limits.

## Alternatives considered

- **Push full blocks to all peers:** Simple but wastes bandwidth and amplifies
  invalid blocks.
- **Gossip-style propagation:** Decoupled and resilient, but harder to
  attribute abuse and reason about duplicate behavior.
- **Compact blocks / short IDs:** Future optimization; deferred to V2.

## Related documents

- `docs/BLOCK_RELAY_ARCHITECTURE.md`
- `docs/RELAY_PROTOCOL_V1.md`
- `docs/RELAY_THREAT_MODEL.md`
- `docs/RELAY_LIMITS_POLICY.md`
