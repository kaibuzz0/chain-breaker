# ADR 015: Header-First Synchronization Strategy

## Status

**Proposed — Phase 8H**

## Context

Chain-Breaker needs a way to bring a new or stale node up to the current chain
tip. The existing network layers (transport, handshake, discovery, gossip)
provide peer connectivity but no chain data exchange. The next phase will define
how nodes download chain data safely.

## Decision

Chain-Breaker will use **header-first synchronization**:

1. Nodes download and validate headers before requesting full blocks.
2. A sparse header locator locates the most recent common ancestor with a peer.
3. Accumulated work is computed from validated headers and compared by the
   Phase 7 reorg engine.
4. Full blocks are downloaded only for header chains that have more work than
   the local best chain.
5. Blocks are validated by the consensus layer before being passed to the
   reorg engine and storage.

Sync will reuse existing Phase 8B message types:

- `GET_HEADERS` / `HEADERS`
- `GET_BLOCK` / `BLOCK`
- `INVENTORY` (future block announcements)

No new wire message types are required for basic sync.

## Consequences

- Bandwidth is conserved because invalid or inferior chains are rejected before
  block download.
- The reorg engine remains the sole authority on fork choice.
- Consensus validation is not duplicated inside the sync layer.
- Implementation complexity is higher than simple full-block download, but the
  security benefits justify it.

## Alternatives considered

- **Full-block download first:** Simpler but wastes bandwidth on invalid or
  low-work chains.
- **UTXO/state sync first:** Faster for light clients but requires trusted
  state snapshots; not appropriate for a full node in this phase.
- **Parallel block download with no header phase:** Higher throughput but
  exposes the node to larger invalid data downloads.

## Related documents

- `docs/SYNC_PROTOCOL_ARCHITECTURE.md`
- `docs/HEADER_SYNC_DESIGN.md`
- `docs/BLOCK_SYNC_DESIGN.md`
- `docs/SYNC_THREAT_MODEL.md`
