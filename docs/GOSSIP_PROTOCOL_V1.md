# Gossip Protocol V1

Version: `chainbreaker-net-v1`  
Status: **Phase 8F design document — architecture/specification only**

---

## 1. Purpose

This document defines the gossip protocol that propagates small, authenticated
announcements across the Chain-Breaker network. In V1 the only gossiped content
is peer reachability hints (PEX) and heartbeat liveness (PING/PONG). Block
headers, transactions, and inventory are explicitly out of scope.

---

## 2. Gossip content V1

Allowed gossip message types:

| Type | Purpose |
|------|---------|
| `PING` | Liveness probe |
| `PONG` | Liveness response |
| `PEX`  | Peer exchange advertisement (future wire type) |

Forbidden in V1 gossip:

- transaction announcements
- block announcements
- inventory batches
- chain state summaries

---

## 3. Message lifecycle

```
Receive gossip message
        |
        v
Envelope validation (Phase 8B parser)
        |
        v
Network ID / genesis / version check (handshake layer)
        |
        v
Duplicate suppression cache lookup
        |
        +-- duplicate --> drop, optionally penalize
        |
        +-- new --> apply peer score filter
                    |
                    v
              Accept locally
                    |
                    v
              Forward according to fanout policy
```

---

## 4. Duplicate suppression

Each gossip message is identified by a `gossip_id` derived from:

```
gossip_id = SHA256(message_type || payload_hash || origin_timestamp)
```

Rules:
- A node remembers every `gossip_id` it has seen for at least
  `gossip_cache_ttl_seconds` (default 300).
- Re-broadcast of a known `gossip_id` is dropped.
- The cache is bounded by `max_gossip_cache_entries` (default 50,000).
- When full, eviction uses FIFO plus a small random sample to resist
  cache-pinning attacks.

---

## 5. TTL and hop limits

Every gossip message carries:

| Field | Default | Meaning |
|-------|---------|---------|
| `ttl` | 3 | remaining hops allowed |
| `hop_count` | 0 | hops already traversed |

Rules:
- A node decrements `ttl` and increments `hop_count` before forwarding.
- Messages with `ttl <= 0` are accepted but not forwarded.
- Messages with `hop_count > max_hops` (default 8) are dropped.
- A node never forwards a message to the peer it received it from.

---

## 6. Fanout policy

When forwarding a new gossip message:

1. Select up to `gossip_fanout` (default 3) active peers.
2. Prefer peers with high score and diverse source.
3. Exclude the incoming peer.
4. Exclude peers that have already sent this `gossip_id`.
5. Send the message; do not wait for acknowledgements.

Fanout is intentionally small to limit bandwidth while still providing
propagation.

---

## 7. Bandwidth controls

Per-peer limits:

| Limit | Default | Behavior on exceed |
|-------|---------|--------------------|
| `max_gossip_per_second` | 10 | drop excess messages |
| `max_gossip_bytes_per_second` | 64 KiB | drop excess messages |
| `max_gossip_payload_size` | 1 KiB | reject message |

Global limits:

| Limit | Default |
|-------|---------|
| `max_total_gossip_per_second` | 100 |
| `max_total_gossip_bytes_per_second` | 512 KiB |

---

## 8. Gossip rules for specific messages

### PING

- Originated periodically by each node toward a random subset of peers.
- `ttl` may be 0 because PING is not propagated.
- PONG response proves reachability.

### PONG

- Sent only in response to a matching PING.
- `ttl` is 0.

### PEX (future)

- Contains a bounded list of peer endpoints (max 16).
- `ttl` default 2.
- Must be rate-limited per peer (max 1 per minute).

---

## 9. Peer scoring interaction

- Forwarding valid, non-duplicate gossip increases the originating peer’s score
  slightly.
- Sending duplicates, invalid messages, or exceeding rate limits decreases
  score.
- A peer that consistently sends gossip that no other peer relays may be
  isolated by diversity scoring.

---

## 10. Determinism

Gossip is intentionally non-deterministic at the network level. A single node
must, however, behave deterministically for a given input:

- Same message seen twice = same suppression decision.
- Same TTL/hop values = same forwarding decision.
- Same peer set and scores = same fanout selection (given a stable random seed).

---

## 11. Security properties

### Bounded amplification

With `ttl=3` and `fanout=3`, the worst-case propagation tree has bounded
size. Combined with duplicate suppression, total network load is finite for a
finite set of nodes.

### No consensus impact

V1 gossip carries no consensus-critical data. A flood of PING/PEX cannot
alter chain state.

### Rate containment

Per-peer and global rate limits prevent a single malicious peer from consuming
disproportionate bandwidth.

---

## 12. Deferred to future phases

- transaction announcements (`INVENTORY`, `TX`)
- block announcements (`BLOCK`, `HEADERS`)
- preferential propagation (e.g., compact blocks)
- privacy-preserving gossip
- epidemic broadcast trees
- cryptographic gossip authentication
