# Phase 8H — Chain Sync Architecture Report

## Status

**Design-only milestone complete.** No sync implementation, no new wire
message behavior, no consensus or storage changes.

## Branch

- `phase8h-sync-architecture-specification`
- Base: `phase8g-discovery-gossip-implementation @ e8e250c`

## Deliverables

| Document | Purpose |
|----------|---------|
| `docs/SYNC_PROTOCOL_ARCHITECTURE.md` | Sync lifecycle, layer responsibilities, phases |
| `docs/HEADER_SYNC_DESIGN.md` | Header-first sync, locator, work comparison |
| `docs/BLOCK_SYNC_DESIGN.md` | Block download, validation-before-storage, ordering |
| `docs/SYNC_THREAT_MODEL.md` | Sync-specific attack analysis |
| `docs/SYNC_LIMITS_POLICY.md` | Request, memory, bandwidth, and retry limits |
| `docs/adr/015-sync-strategy.md` | ADR: header-first strategy |
| `docs/PHASE8H_SYNC_ARCHITECTURE_REPORT.md` | This report |

## Architecture summary

```
Peer:       "I have data."
Sync:       "I can request data."
Consensus:  "This data is valid or invalid."
Reorg:      "This valid chain has greater accumulated work."
Storage:    "Commit the accepted state."
```

Sync phases:

1. **Header discovery** — sparse locator, `GET_HEADERS`, validate headers.
2. **Work comparison** — reorg engine compares accumulated work.
3. **Block download** — sequential or bounded-parallel `GET_BLOCK` requests.
4. **Commit** — reorg engine + storage atomic apply.
5. **Idle** — liveness + periodic re-sync.

## Key design decisions

- **Header-first:** download small headers before large blocks.
- **Locator-based:** sparse ancestor list finds common root efficiently.
- **Consensus-owned validation:** sync never independently decides validity.
- **Reorg-owned fork choice:** sync never chooses the canonical chain.
- **Storage-owned commit:** unvalidated blocks never reach the chain store.
- **Message reuse:** existing `GET_HEADERS`/`HEADERS`/`GET_BLOCK`/`BLOCK` are
  sufficient for basic sync.

## Threat review

| Threat | Mitigation |
|--------|------------|
| Fake high-work chain | Validate headers; compute work locally |
| Invalid header flooding | Incremental validation; rate limits; score penalties |
| Invalid block flooding | Header-first; per-block validation; bans |
| Bandwidth exhaustion | Byte limits; bounded response sizes |
| Eclipse attacks | Multiple sync peers; diversity rules |
| Slow peers | Timeouts; retries; parallel requests |
| Malformed responses | Schema validation; envelope parser |
| Resource exhaustion | Bounded queues, caches, memory limits |
| Deep reorg abuse | Reorg certification; score penalties |

## Unresolved questions

- Whether and where to introduce consensus checkpoints for eclipse resistance.
- The exact parallelism model for block download in Phase 8I.
- Archive synchronization sequencing relative to chain sync.
- Light client / simplified-payment-verification strategy (deferred beyond V1).

## Future implementation boundary

Phase 8I will implement the sync layer. It must:

- use existing message types
- integrate with Phase 8G discovery and Phase 8D/E transport
- delegate validation to consensus
- delegate fork choice to the Phase 7 reorg engine
- commit only through Phase 7 storage
- enforce the limits defined in `docs/SYNC_LIMITS_POLICY.md`

## Verification

- No Python source code added.
- `ruff check chainbreaker tests` ✅
- `mypy chainbreaker tests/network` ✅
- `pytest tests/network/` ✅
- `python -m build --wheel` ✅
- `bandit -r chainbreaker/network` ✅

## Out of scope (explicitly)

- sync implementation
- new wire message types
- transaction relay
- mempool
- block announcement gossip dispatch
- mining communication
- checkpoint consensus rules

## Conclusion

Phase 8H defines a safe, bounded synchronization architecture that preserves
the consensus/reorg/storage authority established in Phase 7. The sync layer is
a requestor and courier, not a decision-maker. Implementation awaits explicit
authorization in **Phase 8I — Chain Sync Implementation**.
