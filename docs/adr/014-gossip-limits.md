# ADR 014: Gossip Limits for V1

## Status

**Proposed — Phase 8F**

## Context

Once peers are connected, nodes need a controlled way to exchange small,
non-critical announcements (liveness probes, peer exchange hints). Unbounded
gossip is a classic amplification vector, so V1 must define strict limits.

## Decision

V1 gossip will be **bounded and content-limited**:

- Allowed message types: `PING`, `PONG`, `PEX` (future).
- Forbidden in V1 gossip: transaction, block, and inventory announcements.
- Each message carries `ttl` (default 3) and `hop_count`.
- Fanout is capped at `gossip_fanout=3` peers.
- Duplicate suppression via `gossip_id` with a 5-minute cache and 50,000-entry
  cap.
- Per-peer and global rate limits prevent bandwidth abuse.

Gossip behavior must be deterministic for a given node state but is not
expected to be globally deterministic.

## Consequences

- Amplification is bounded by TTL × fanout and duplicate suppression.
- V1 cannot yet propagate blocks or transactions through gossip.
- A later phase can add inventory/block gossip without changing the core
  propagation rules.

## Alternatives considered

- **Epidemic broadcast trees:** More efficient but require more topology state
  and are unnecessary for the tiny V1 gossip payload set.
- **Full-flood gossip:** Simpler but unbounded and unacceptable for resource
  safety.

## Related documents

- `docs/GOSSIP_PROTOCOL_V1.md`
- `docs/PEER_SCORING_MODEL.md`
- `docs/NETWORK_TOPOLOGY_THREAT_MODEL.md`
