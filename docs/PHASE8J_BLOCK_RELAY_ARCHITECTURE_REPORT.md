# Phase 8J — Block Relay Architecture Report

## Status

**Design-only milestone complete.** No relay implementation, no new wire
behavior, no consensus changes.

## Branch

- `phase8j-block-relay-architecture`
- Base: `phase8i-chain-sync-implementation @ 9fe0c91` (HEAD `c3dc24e` after local checkout)

## Deliverables

| Document | Purpose |
|----------|---------|
| `docs/BLOCK_RELAY_ARCHITECTURE.md` | Relay lifecycle, propagation, orphan handling |
| `docs/RELAY_PROTOCOL_V1.md` | Message semantics, request/response flow, rate limits |
| `docs/RELAY_THREAT_MODEL.md` | Relay-specific attack analysis |
| `docs/RELAY_LIMITS_POLICY.md` | Inventory, cache, orphan, bandwidth limits |
| `docs/adr/016-block-relay-strategy.md` | ADR: inventory/pull model |
| `docs/PHASE8J_BLOCK_RELAY_ARCHITECTURE_REPORT.md` | This report |

## Architecture summary

```text
Local node validates block
        |
        v
INV_BLOCK to selected peers
        |
        v
Peers request GET_BLOCK
        |
        v
BLOCK delivered
        |
        v
Peer validates independently
        |
        v
Peer relays further
```

## Key design decisions

- **Pull model:** announcements are small; full blocks only on request.
- **No new message types:** reuse `INV_BLOCK`, `GET_BLOCK`, `BLOCK`, optional
  `REJECT_BLOCK`.
- **Validation before relay:** consensus must accept a block before it is
  forwarded.
- **Duplicate suppression:** bounded seen-cache prevents amplification.
- **Bounded orphan pool:** 1024 entries, 2-hour max age, one parent request.
- **Rate and bandwidth limits:** per-peer and global budgets.
- **Separation from sync:** sync catches up; relay propagates the tip.

## Threat review

| Threat | Mitigation |
|--------|------------|
| Block flooding | INV size limits, rate limits, validation before relay |
| Duplicate amplification | RelaySeenCache, 50k entries, 2h TTL |
| Orphan flooding | 1024-entry orphan pool, age limit, no relay of orphans |
| Bandwidth exhaustion | Response byte limits, global/per-peer budgets |
| Invalid block injection | Mandatory validation, score penalties |
| Eclipse-assisted relay | Multiple peers, diversity rules, sync still active |
| Withholding / slow relay | Parallel requests, timeouts, retries |

## Unresolved questions

- Exact sync/relay handoff threshold (e.g., height difference).
- Whether to use gossip engine for INV propagation.
- Compact-block / short-id protocol timing.
- Anchor block / checkpoint policy.

## Future implementation boundary

Phase 8K will implement block relay. It must:

- use existing message types
- integrate with the Phase 8G peer table for peer selection
- use Phase 8D/E transport for delivery
- delegate validation to consensus
- enforce the limits in `docs/RELAY_LIMITS_POLICY.md`
- remain separate from sync and mempool

## Verification

- No Python source code added.
- `ruff check chainbreaker tests` ✅
- `mypy chainbreaker tests/network` ✅
- `pytest tests/network/` ✅
- `python -m build --wheel` ✅
- `bandit -r chainbreaker/network` ✅

## Out of scope (explicitly)

- transaction relay
- mempool
- fee market
- mining pool behavior
- economic layer
- consensus changes

## Conclusion

Phase 8J defines a bounded, pull-based block relay architecture that avoids
broadcast amplification, protects against orphan flooding, and keeps the
consensus boundary intact. Implementation awaits explicit authorization in
**Phase 8K — Block Relay Implementation**.
