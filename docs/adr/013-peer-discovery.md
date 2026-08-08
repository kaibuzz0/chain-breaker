# ADR 013: Peer Discovery Architecture for V1

## Status

**Proposed — Phase 8F**

## Context

Chain-Breaker needs a way for nodes to find peers after the transport and
handshake layers (Phases 8C–8E) are in place. Discovery is the next
foundational network layer, but it must not introduce consensus, storage, or
mempool coupling.

## Decision

V1 peer discovery will use a **multi-source, trust-minimized, outbound-only**
model:

1. **Static bootstrap list** as the primary startup source.
2. **DNS seeds** for diversity and operator-independent liveness.
3. **Manual peer configuration** for operator-controlled deployments.
4. **PEX wire message** defined but not mandatory in V1.
5. **Cached recent peers** to reduce bootstrap dependency across restarts.

Peer identities will be **ephemeral and anonymous** for V1. Reputation is keyed
by session `peer_id`, not by a long-lived public key.

## Consequences

- Simplicity: no PKI, no DHT, no NAT traversal.
- Eclipse resistance is partial; diversity rules and independent seeds raise
  cost but do not eliminate the threat.
- Future upgrade to persistent cryptographic identity is possible without
  changing the discovery mechanics.
- Outbound-only model avoids exposing a public listening port in V1.

## Alternatives considered

- **DHT (Kademlia):** More decentralized but adds significant complexity,
  Sybil attack surface, and operational risk before gossip/sync behavior is
  defined.
- **Permanent PKI identity:** Stronger Sybil resistance but expands the trust
  surface and key-management requirements prematurely.
- **Inbound listening in V1:** Increases exposed attack surface; deferred.

## Related documents

- `docs/PEER_DISCOVERY_ARCHITECTURE.md`
- `docs/NETWORK_TOPOLOGY_THREAT_MODEL.md`
