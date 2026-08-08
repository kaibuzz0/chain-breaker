# Phase 8F — Peer Discovery & Gossip Architecture Report

## Status

**Design-only milestone complete.** No implementation code, no new runtime
behavior, no consensus or storage changes.

## Branch

- `phase8f-discovery-gossip-architecture`
- Base: `phase8e-socket-transport @ 61e3457`

## Deliverables

| Document | Purpose |
|----------|---------|
| `docs/PEER_DISCOVERY_ARCHITECTURE.md` | Multi-source peer discovery model |
| `docs/GOSSIP_PROTOCOL_V1.md` | Bounded gossip rules for V1 |
| `docs/PEER_SCORING_MODEL.md` | Peer reputation and ban policy |
| `docs/NETWORK_TOPOLOGY_THREAT_MODEL.md` | Sybil/eclipse/flood threat analysis |
| `docs/adr/013-peer-discovery.md` | ADR: discovery architecture choice |
| `docs/adr/014-gossip-limits.md` | ADR: gossip limit decision |
| `docs/PHASE8F_DISCOVERY_GOSSIP_ARCHITECTURE_REPORT.md` | This report |

## Architecture summary

```
Application services
       |
Sync / Relay (future)
       |
Gossip Engine (V1: PING/PONG/PEX only)
       |
Peer Discovery Layer
       |
Connection Manager (Phase 8D)
       |
TCP Transport (Phase 8E)
       |
Network Envelope + Parser (Phases 8B)
```

## Key design decisions

1. **Discovery sources:** static bootstrap, DNS seeds, manual config, PEX
   (future), cached peers.
2. **Peer identity:** ephemeral anonymous `peer_id` for V1; persistent
   cryptographic identity deferred.
3. **Gossip content:** only liveness and peer-exchange announcements in V1.
4. **Gossip limits:** TTL=3, fanout=3, duplicate cache 5 min / 50k entries,
   per-peer and global rate limits.
5. **Peer scoring:** 0–1000 scale, dynamic bans with escalating durations,
   local-only scores, recovery mechanism.
6. **Topology threats:** Sybil, eclipse, gossip flooding, duplicate cache abuse,
   topology manipulation, seed compromise documented with mitigations.

## Security invariants

- No single peer is trusted.
- Scores are local only.
- Gossip amplification is bounded.
- Discovery uses multiple independent sources.
- Topology state never influences consensus or storage.

## Verification

- No Python source code added.
- `ruff check chainbreaker tests` ✅
- `mypy chainbreaker tests/network` ✅
- `pytest tests/network/` ✅
- `python -m build --wheel` ✅
- `bandit -r chainbreaker/network` ✅

## Out of scope (explicitly)

- peer discovery implementation
- gossip engine implementation
- PEX wire message implementation
- transaction/block/inventory gossip
- sync engine
- mempool networking
- inbound listening / NAT traversal
- persistent cryptographic node identity

## Conclusion

Phase 8F documents a controlled, threat-aware design for the next network
layers. The project can now proceed to **Phase 8G — Peer Discovery & Gossip
Implementation** with a reviewed specification, or to a later phase, only after
explicit authorization.
