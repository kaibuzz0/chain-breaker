# Phase 8A — Network Architecture Specification Report

## Status

**Design-only milestone.** No networking code, no sockets, no peer
implementation, no Protocol V2 changes.

## Branch

- `phase8a-network-architecture-specification`
- Base: `main @ 203a6e3`

## Deliverables

| Document | Purpose |
|----------|---------|
| `docs/NETWORK_PROTOCOL_V1.md` | Wire format, message envelope, typed payloads, failure behavior |
| `docs/PEER_HANDSHAKE.md` | HELLO / HELLO_ACK flow, validation rules, rejection conditions |
| `docs/NETWORK_THREAT_MODEL.md` | Identity, transport, consensus, and resource attacks |
| `docs/SYNC_ARCHITECTURE.md` | Header, block, state, and archive sync order |
| `docs/PEER_LIMITS_POLICY.md` | Message, connection, rate, and memory limits |
| `docs/NETWORK_CONSENSUS_BOUNDARY.md` | Hard line between network transport and consensus decisions |
| `docs/NETWORK_ARCHITECTURE_ADVERSARIAL_REVIEW.md` | Attempted break of the design, mitigations, residual risks |
| `docs/adr/010-network-boundary.md` | ADR: network is an outer subsystem |
| `docs/adr/011-peer-validation.md` | ADR: peers are untrusted data sources |
| `docs/adr/012-sync-strategy.md` | ADR: sync order is headers → blocks → state → archive |

## Core design decisions

1. **Envelope-header layout.** Fixed fields: magic, protocol version, network
   ID length, network ID, message type, flags, payload length, payload hash,
   payload. All limits enforced before payload allocation.
2. **JSON payloads in V1.** Binary fields hex-encoded. Future versions may
   add binary payload encoding.
3. **HELLO/HELLO_ACK handshake.** Genesis hash and network ID are
   non-negotiable constants. Mismatch → immediate disconnect.
4. **Sync order is strict.** Headers first, blocks second, state replayed
   locally from canonical blocks, archive objects fetched lazily by content
   hash.
5. **No peer identity in V1.** Identity, reputation, and encryption are
   deferred to later phases.
6. **Consensus boundary is one-way.** Network may call consensus validation;
   consensus never imports network.

## Threat coverage

| Attack class | Covered in | Mitigation summary |
|--------------|------------|-------------------|
| Sybil / fake identities | `NETWORK_THREAT_MODEL.md` | No identity to fake; connection limits; no peer authority |
| Peer flooding / eclipse | `NETWORK_THREAT_MODEL.md` | Operator-controlled outbound peers; independent validation |
| Oversized messages | `NETWORK_PROTOCOL_V1.md`, `PEER_LIMITS_POLICY.md` | `MAX_PAYLOAD_BYTES` before allocation |
| Malformed length prefixes | `NETWORK_PROTOCOL_V1.md` | Bounded reads, timeout disconnect |
| Amplification | `NETWORK_PROTOCOL_V1.md` | Response size caps, batch limits |
| Slow peers | `PEER_LIMITS_POLICY.md` | Handshake, read, and idle timeouts |
| Fake high-work chains | `SYNC_ARCHITECTURE.md` | Local work computation; full block validation |
| Invalid block spam | `SYNC_ARCHITECTURE.md` | Validate before storage/relay |
| Fork flooding / reorg abuse | `SYNC_ARCHITECTURE.md`, `NETWORK_CONSENSUS_BOUNDARY.md` | Equal-work no-switch; reorg engine for all inputs |
| Alternate genesis | `PEER_HANDSHAKE.md` | Genesis constant, no negotiation |
| Memory exhaustion | `PEER_LIMITS_POLICY.md` | Limits before allocation, per-peer/global budgets |
| CPU exhaustion | `PEER_LIMITS_POLICY.md` | Rate limits, PoW-first validation |
| Disk exhaustion | `PEER_LIMITS_POLICY.md` | Orphan caps, content-addressed archive |
| Archive poisoning | `SYNC_ARCHITECTURE.md` | Content-hash verification; provenance from canonical blocks |
| Bypass of Protocol V2 | `NETWORK_CONSENSUS_BOUNDARY.md`, ADR 010 | Consensus core is network-free |

## Explicit non-goals for V1

The following are **not** in Phase 8A or V1:

- peer discovery / address gossip
- socket implementation
- NAT traversal
- transport encryption
- peer database / reputation
- mempool / transaction relay policy
- block template distribution
- light client protocol
- payment channels

These belong to later phases.

## Adversarial review outcome

The architecture resists the identified attacks. The remaining risks are:

1. Transport-level DDoS (operational, outside protocol scope).
2. Eclipse if all operator peers are malicious (operational diversity required).
3. No transport encryption (deferred).
4. No peer identity / reputation (deferred).
5. Future dangerous message types (mitigated by code review and ADR 010).

## Consensus boundary verification

No consensus files were modified in Phase 8A:

- `chainbreaker/block.py` — untouched
- `chainbreaker/consensus/protocol_v2.py` — untouched
- `chainbreaker/codec.py` — untouched
- `chainbreaker/crypto.py` — untouched
- `chainbreaker/reorg.py` — untouched
- `chainbreaker/storage/backend.py` — untouched
- `vectors/` — untouched

## Verification run

- `ruff check chainbreaker tests` — passing
- `mypy chainbreaker` — passing
- `python -m build --wheel` — passing

## Success criteria

- [x] Wire format documented
- [x] Handshake documented
- [x] Threat model complete
- [x] Sync model defined
- [x] Peer limits defined
- [x] Consensus boundary frozen
- [x] Adversarial review completed
- [x] No consensus code modified
- [x] No networking code implemented

## Recommendation

Phase 8A is complete. The next milestone should be **Phase 8B — Network
Protocol Implementation**, only after this design is reviewed and approved.
Networking code should not be written until the architecture boundary is
explicitly accepted.
