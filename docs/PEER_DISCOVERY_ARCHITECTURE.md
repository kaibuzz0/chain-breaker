# Peer Discovery Architecture

Version: `chainbreaker-net-v1`  
Status: **Phase 8F design document — architecture/specification only**

---

## 1. Purpose

This document defines how a Chain-Breaker node discovers and maintains its
initial set of peers. It intentionally does not define gossip rules,
synchronization logic, transaction relay, or mempool behavior.

---

## 2. Design principles

1. **No single source of truth.** Peer discovery must tolerate bootstrap
   failures, partial deception, and transient partitions.
2. **Diversity first.** A healthy node must maintain connections across
   independent peer sources, autonomous systems, and identity domains where
   possible.
3. **Fail safely.** When discovery fails, the node must fall back to an
   explicitly authorized set of bootstrap peers or enter a safe idle state.
4. **No consensus coupling.** Discovery must not depend on chain state,
   registry contents, archive data, or governance decisions.
5. **Sybil-aware, not Sybil-proof.** Phase 8F recognizes Sybil resistance as an
   open problem and designs mechanisms that raise cost rather than claim
   perfection.

---

## 3. Peer identity model

For discovery V1, Chain-Breaker uses **ephemeral anonymous peer identities**:

- Each connection receives a local `peer_id` generated per session.
- The `peer_id` is not authenticated by public key in V1.
- Reputation state is keyed by the `peer_id` of an established session.
- Long-lived identity, cryptographic authentication, and anti-Sybil proofs are
  deferred to a later phase.

Rationale:
- Simplicity: handshake already validates `network_id`, `genesis_hash`, and
  `protocol_version`; adding PKI in V1 would expand the trusted surface before
  gossip or sync behavior is defined.
- Future: a later phase can upgrade peer identity to persistent public keys
  without changing discovery mechanics.

---

## 4. Peer lifecycle

```
UNKNOWN
   |
   v
BOOTSTRAP_CANDIDATE  (from seed/cache/list)
   |
   v
CONNECTING           (transport open in progress)
   |
   v
HANDSHAKE            (HELLO/HELLO_ACK validation)
   |
   +-- success --> ACTIVE_PEER
   |
   +-- failure --> REJECTED
                    |
                    v
              PENALIZED / BANNED (scoring layer)
                    |
                    v
              EVICTED (from peer table)
```

States are managed by the connection manager (Phase 8D) and the future peer
pool. Discovery is responsible for producing candidates, not for managing
established sessions.

---

## 5. Discovery sources

Phase 8F defines the following ordered sources of peer candidates.

### 5.1 Static bootstrap list

A configuration file contains a small set of trusted bootstrap endpoints.

Format:

```yaml
bootstrap_peers:
  - host: seed.chainbreaker.example
    port: 8333
    trusted: true
  - host: 192.0.2.10
    port: 8333
    trusted: false
```

Properties:
- First source consulted at startup.
- Trusted entries are used even if other discovery mechanisms fail.
- Untrusted entries are treated as ordinary candidates.
- Must support hostnames, IPv4, and IPv6.

### 5.2 DNS seeds

A set of DNS names that resolve to multiple A/AAAA records, each yielding a
candidate endpoint.

Properties:
- Provides diversity from a single query.
- Trusts the DNS operator for liveness, not for correctness.
- Records are ephemeral; discovered peers are scored like any other candidate.

### 5.3 Manual peer configuration

Operator-provided peer addresses via config, CLI, or RPC.

Properties:
- Highest trust tier (operator intent).
- Bypasses scoring initially; still validated by handshake.

### 5.4 Peer exchange (PEX)

After a successful handshake, a peer may advertise a bounded list of peers it
knows. PEX is a future protocol message type; V1 documents the format and
limits but does not require implementation in Phase 8F.

Properties:
- Decentralized discovery without dedicated seed operators.
- Vulnerable to eclipse if a node relies only on its current peers for new
  peers.
- Must be rate-limited and diversity-checked.

### 5.5 Cached peers

On graceful shutdown a node may persist a small set of recently active peers.

Properties:
- Reduces bootstrap dependency across restarts.
- Cached peers are still re-validated by handshake.
- Cache must expire stale entries and must not persist banned peers.

---

## 6. Peer table

The peer table is an in-memory data structure that holds known peer endpoints
and metadata.

Fields per entry:

| Field | Description |
|-------|-------------|
| `endpoint` | `(host, port)` tuple |
| `source` | bootstrap, dns, manual, pex, cache |
| `last_seen` | timestamp of last successful connection |
| `last_attempt` | timestamp of last connection attempt |
| `failure_count` | consecutive failed attempts |
| `score` | current reputation score |
| `capabilities` | feature bits from last handshake |

Capacity:
- `max_peer_table_entries`: 4096 by default.
- When full, eviction prefers oldest, lowest-score, duplicate-source entries.

---

## 7. Diversity rules

To resist eclipse, the peer table and active connections enforce source
diversity:

- No more than `max_same_source_ratio` (default 0.25) of active peers may
  come from a single discovery source.
- No more than `max_same_as_peers` (default 2) active peers may share the same
  /24 IPv4 prefix or /48 IPv6 prefix.
- Trusted manual/bootstrap peers are exempt from source diversity but still
  count toward total connection limits.

---

## 8. Connection policy

From the peer table, the node selects active connections using:

1. Mandatory trusted/manual peers if configured.
2. A random sample weighted by score and recency.
3. At least one peer from each enabled discovery source, if available.
4. Respecting `max_outbound_connections` (default 8).

Outbound-only model in V1. Inbound listening is a later phase.

---

## 9. Security analysis

### 9.1 Sybil

Discovery V1 does not prevent an attacker from claiming many IP addresses or
identities. Defenses:
- source diversity limits
- scoring and ban policy
- multiple independent bootstrap sources
- future upgrade to identity-bound reputation

### 9.2 Eclipse

An attacker who controls a node’s peers can isolate it. Defenses:
- maintain peers from independent sources
- periodic random reconnection to bootstrap/DNS seeds
- diversity limits on IP prefixes and sources
- future: deterministic anchor peers and out-of-band checks

### 9.3 Bootstrap compromise

A compromised seed can feed only attacker addresses. Defenses:
- use multiple independent seeds
- cross-check against cached/manual peers
- treat all bootstrap candidates as untrusted until handshake succeeds

### 9.4 Enumeration

An attacker scans the network to map topology. Defenses (V1 limited):
- outbound-only model reduces exposed surface
- PEX responses are bounded and randomized
- future: privacy-preserving peer exchange

---

## 10. Deferred to future phases

- persistent cryptographic node identity
- inbound listening and NAT traversal
- DHT or fully decentralized discovery
- peer exchange (PEX) wire implementation
- deterministic anchor peer selection
- privacy-preserving peer discovery

---

## 11. Relation to other layers

Discovery feeds the connection manager. It must not:
- validate blocks or transactions
- read from storage
- query the registry or archive
- make consensus decisions

All candidates are validated only by the existing handshake layer.
