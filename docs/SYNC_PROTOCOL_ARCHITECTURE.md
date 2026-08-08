# Sync Protocol Architecture

Version: `chainbreaker-net-v1`  
Status: **Phase 8H design document — architecture/specification only**

---

## 1. Purpose

This document defines the architecture for synchronizing a Chain-Breaker node
with the network. It intentionally does not implement synchronization
behavior, new wire messages, or peer logic. Its goal is to specify the
responsibilities, phases, and safety boundaries of the sync subsystem before
any code is written.

---

## 2. Core invariant

```
Peer:       "I have data."
Sync:       "I can request data."
Consensus:  "This data is valid or invalid."
Reorg:      "This valid chain has greater accumulated work."
Storage:    "Commit the accepted state."
```

The sync subsystem **must not** decide which chain is canonical. It may only:

- discover that a peer claims to have headers/blocks
- request those headers/blocks
- deliver them to the consensus validation layer
- apply the result decided by consensus and the reorg engine

---

## 3. Synchronization lifecycle

```
BOOTSTRAP
    |
    v
DISCOVER_PEERS          (Phase 8G discovery)
    |
    v
HANDSHAKE               (Phase 8D handshake)
    |
    v
SELECT_SYNC_PEERS       (high-score, diverse peers)
    |
    v
HEADER_SYNC             (download + validate headers)
    |
    v
HEADER_VALIDATION       (consensus: POW, adjacency, rules)
    |
    v
WORK_COMPARISON         (reorg engine: accumulated work)
    |
    +-- no better chain --> IDLE
    |
    +-- better chain --> BLOCK_SYNC
    |                           |
    |                           v
    |                   DOWNLOAD_BLOCKS
    |                           |
    |                           v
    |                   BLOCK_VALIDATION
    |                           |
    |                           v
    |                   REORG_EVALUATION  (Phase 7 reorg engine)
    |                           |
    |                           v
    |                   STORAGE_COMMIT  (Phase 7 storage)
    |                           |
    |                           v
    |                       IDLE
    |
    v
CRASH_RECOVERY          (resume from storage snapshot)
```

---

## 4. Node bootstrap flow

When a node starts with an empty or stale chain:

1. Load the last committed chain state from storage.
2. Run discovery (Phase 8G) to obtain candidate peers.
3. Open connections and complete handshakes.
4. Select one or more sync peers from the active set using score and diversity.
5. Begin header synchronization from the local best header backward to genesis,
   building a compact locator.
6. Request headers after the best common ancestor.
7. Validate headers and compare total work.
8. If a better chain is found, download blocks in order and commit via the
   reorg engine.
9. Transition to idle/liveness mode (PING/PONG) with periodic re-sync triggers.

---

## 5. Layer responsibilities

### 5.1 Discovery layer (Phase 8G)

- Provide candidate peers.
- Maintain peer scores.
- Enforce diversity rules.
- **Sync must not** ask discovery to validate chain data.

### 5.2 Transport layer (Phases 8C–8E)

- Move bytes between nodes.
- Frame envelopes.
- Enforce timeouts and limits.
- **Sync must not** interpret payload semantics at the transport layer.

### 5.3 Handshake layer (Phase 8D)

- Prove protocol/network/genesis compatibility.
- Exchange capability bits.
- **Sync must not** trust a peer’s claimed best height or chain work.

### 5.4 Sync layer (future Phase 8I)

- Schedule requests.
- Track outstanding downloads.
- Detect timeouts.
- Queue data for validation.
- Apply the consensus decision to storage.
- **Sync must not** independently decide validity or canonicality.

### 5.5 Consensus validation

- Validate every header and block against Protocol V2 rules.
- Return valid/invalid.
- **Consensus is authoritative.**

### 5.6 Reorg engine (Phase 7H)

- Compare accumulated work of valid candidate chains.
- Select the chain with the greatest work.
- Produce a reorg certification if switching.
- **Reorg engine is authoritative for fork choice.**

### 5.7 Storage (Phase 7E–7G)

- Persist only committed, validated state.
- Provide crash recovery anchor.
- **Storage commits only after consensus + reorg approval.**

---

## 6. Sync phases

### 6.1 Phase 1 — Header discovery

Goal: find the best chain the network knows about without downloading full
blocks.

- Build a header locator from local chain tip back to genesis (max 32 entries).
- Send `GET_HEADERS` with the locator.
- Receive `HEADERS` containing up to 2000 consecutive headers.
- Validate each header immediately.

### 6.2 Phase 2 — Work comparison

Goal: decide whether the peer's chain is better than the local chain.

- Compute total accumulated work of the received header chain.
- Compare to local best chain work using the reorg engine.
- If the received chain is not better, stop.
- If the received chain is better, proceed to block download.

### 6.3 Phase 3 — Block download

Goal: obtain full blocks for the better header chain.

- Request blocks by hash (`GET_BLOCK`).
- Enforce download order to allow streaming validation.
- Bound outstanding requests and memory.
- Validate each block before requesting the next batch.

### 6.4 Phase 4 — Commit

Goal: make the new chain durable.

- Reorg engine evaluates the validated chain.
- Storage applies the reorg and commits atomically.
- Update local best height/chain work.

### 6.5 Phase 5 — Idle

Goal: maintain synchronization with minimal bandwidth.

- Listen for block announcements via future inventory gossip.
- Periodically re-check headers if local tip is stale.
- Use liveness probes to monitor sync peers.

---

## 7. Failure boundaries

| Failure | Sync response |
|---------|---------------|
| Invalid header | Reject, penalize peer, stop using this chain |
| Invalid block | Reject, penalize peer, stop using this chain |
| Timeout | Retry with another peer, reduce score |
| Partial response | Re-request missing data |
| Better chain loses later | Reorg engine reverses decision; storage rolls back |
| Crash mid-sync | Resume from last committed snapshot; do not trust partial download |
| Malformed sync message | Parser rejects; peer penalized |

---

## 8. Message types used

Sync will reuse existing Phase 8B message types:

- `GET_HEADERS`
- `HEADERS`
- `GET_BLOCK`
- `BLOCK`
- `INVENTORY` (future, for block announcement gossip)
- `REJECT` (for explicit sync rejection)

No new wire message types are required for header/block sync.

---

## 9. Relation to other layers

Sync may call:

- discovery for candidate peers
- transport to send/receive messages
- consensus validation functions
- reorg engine work comparison
- storage read/write after approval

Sync must not:

- modify consensus rules
- modify storage schema
- bypass the reorg engine
- trust peer claims without validation
- leak sync state into gossip or discovery
