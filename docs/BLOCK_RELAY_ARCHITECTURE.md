# Block Relay Architecture

Version: `chainbreaker-net-v1`  
Status: **Phase 8J design document — architecture/specification only**

---

## 1. Purpose

This document defines the architecture for relaying newly validated blocks
between Chain-Breaker nodes. It is a design-only phase; no implementation code,
new wire messages, or peer behavior is added yet.

Block relay answers:

> "A node has a new valid block. How does that information efficiently reach
> other nodes?"

It is distinct from chain sync, which answers:

> "A node is behind. How does it catch up?"

---

## 2. Core principles

1. **Relay only what the local node has validated.**
   A block is never forwarded before the local consensus layer accepts it.

2. **Pull, not push.**
   Announcements are small. Full blocks are sent only in response to explicit
   requests. This prevents bandwidth abuse.

3. **Duplicate suppression.**
   A block seen once is not announced or requested again within the cache
   window.

4. **Orphan blocks are bounded.**
   A block whose ancestor is unknown is held temporarily in an orphan pool
   with strict size and age limits.

5. **Relay does not decide canonicality.**
   Consensus validates. The reorg engine chooses. Relay only propagates
   information.

---

## 3. Relay message types

Phase 8J reuses existing message types and reserves future names:

| Message | Direction | Purpose |
|---------|-----------|---------|
| `INV_BLOCK` | outbound | Announce a newly accepted block hash to peers. |
| `GET_BLOCK` | outbound | Request a block by hash from a peer. |
| `BLOCK` | inbound/outbound | Deliver one or more blocks in response. |
| `REJECT_BLOCK` | outbound | Explicitly reject an invalid block after validation. |

No new message types are required for block relay in V1.

---

## 4. Block announcement lifecycle

```text
Local node receives or mines block B
        |
        v
Consensus validates B
        |
        +-- invalid --> discard, optionally penalize source
        |
        +-- valid --> insert into local chain / mempool side
        |
        v
Add B to relay seen-cache
        |
        v
Build INV_BLOCK for subset of peers
        |
        v
Send INV_BLOCK to selected peers
        |
        v
Peer receives INV_BLOCK
        |
        v
Check duplicate cache
        |
        +-- duplicate --> ignore
        |
        +-- new --> check interest
        |
        v
If behind or competing chain:
    send GET_BLOCK(B)
        |
        v
Peer sends BLOCK(B)
        |
        v
Local node validates B independently
        |
        +-- invalid --> reject, penalize peer
        |
        +-- valid --> add to chain, repeat announcement cycle
```

---

## 5. Interaction with sync

| Situation | Responsible subsystem |
|-----------|----------------------|
| Node is far behind | Sync engine (Phase 8I) |
| Node is near tip | Block relay |
| A block arrives during sync | Relay queues it; sync applies it if relevant |
| A sync response contains a block | Sync engine handles it directly |

Relay operates when the node is mostly synced. Sync operates when the node is
significantly behind. A future phase will define the handoff boundary.

---

## 6. Orphan handling

An orphan is a block whose `prev_hash` is not in the local chain and is not
already known as another orphan.

Orphan pool rules:

- Maximum size: 1024 entries.
- Maximum age: 2 hours.
- On receiving an orphan, request its missing parent.
- If the parent arrives and connects a chain, process the chain in order.
- Orphans that never connect are evicted by age or by pool overflow.
- Orphans are not relayed.

---

## 7. Propagation strategy

### 7.1 Fanout

- A node forwards an `INV_BLOCK` to up to 8 connected peers.
- Selection prefers peers with high scores and diverse network addresses.
- The originating peer is not re-announced to.

### 7.2 Delay

- A small, deterministic delay (e.g., 50–200 ms) may be used before
  announcement to allow compact-block or short-id protocols in the future.
- Phase 8J does not require delay; it documents the extension point.

### 7.3 Re-request

- If a requested block is not received within the timeout, retry with
  another peer that announced the same hash.
- Maximum retries per hash: 3.

---

## 8. Validation boundaries

Relay must call consensus validation for every received block before:

- adding it to the chain
- adding it to the orphan pool
- forwarding it to peers
- acknowledging it to the requestor

Relay must not:

- trust a peer’s `INV_BLOCK` claim
- bypass the ledger validation path
- write unvalidated blocks to storage

---

## 9. Failure modes

| Failure | Response |
|---------|----------|
| Invalid block in `BLOCK` response | Reject, penalize peer, drop block |
| Orphan storm | Enforce pool size/age limits |
| Duplicate `INV_BLOCK` | Use seen-cache, ignore |
| Unsolicited `BLOCK` | Validate; if unknown and valid, treat as orphan |
| Peer never responds to `GET_BLOCK` | Timeout, retry with another peer |
| Large `BLOCK` response | Enforce `MAX_BLOCKS_RESPONSE` and byte limits |

---

## 10. Relation to other components

- **Transport**: moves `INV_BLOCK`, `GET_BLOCK`, `BLOCK` envelopes.
- **Gossip engine**: could carry announcements, but block relay uses direct
  peer messages for reliability and accountability.
- **Sync engine**: requests historical blocks during catch-up.
- **Consensus/ledger**: validates every relayed block.
- **Reorg engine**: decides whether a relayed block activates a new tip.
- **Storage**: persists only validated, committed blocks.
