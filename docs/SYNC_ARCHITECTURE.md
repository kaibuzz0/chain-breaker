# Synchronization Architecture

Version: `chainbreaker-net-v1`  
Status: **architecture specification — no implementation yet**

---

## 1. Purpose

Define how a Chain-Breaker node reconciles its local chain and state with the
network. The sync layer sits **above** the wire protocol and **below** the
consensus engine. It requests data from peers, passes it to the consensus
engine for validation, and updates local storage only on success.

The core rule continues:

> The network proposes data. The consensus engine accepts or rejects it.

---

## 2. Sync phases

Synchronization happens in strict order:

```
headers
   |
   v
blocks
   |
   v
state verification
   |
   v
archive objects (lazy)
```

A node must not request state or archive objects for heights it has not
validated as canonical blocks.

---

## 3. Header synchronization

### 3.1 Goal

Download enough headers to determine which chain has the greatest accumulated
valid work.

### 3.2 Flow

```
Local node                             Peer
   |                                    |
   |--- GET_HEADERS(start, stop, N) --->|
   |                                    |
   |<----------- HEADERS ---------------|
   |                                    |
   |     validate each header           |
   |     check PoW                      |
   |     check linkage                  |
   |     compute accumulated work       |
   |                                    |
   |  if peer chain has more work:      |
   |     request blocks                 |
```

### 3.3 GET_HEADERS semantics

A `GET_HEADERS` request contains:

- `start_hashes`: one or more block hashes where the peer should begin.
  The peer returns the first hash it recognizes, then the following headers.
- `stop_hash`: the hash to stop at (inclusive). Empty means "as many as the
  limit allows."
- `max_count`: maximum number of headers to return.

If none of the `start_hashes` are on the peer's chain, the peer returns an
empty `HEADERS` response.

### 3.4 HEADERS validation

For each received header, the local node must independently verify:

1. Header is valid V2 (correct size, version, fields).
2. `prev_hash` links to a known header.
3. PoW satisfies the header's target.
4. Timestamp and median-past-time rules hold.
5. The accumulated work across the returned chain is computed locally.

A peer **never** tells the node what the accumulated work is. The node
computes it.

### 3.5 Locator strategy

When a node is far behind, it sends multiple `start_hashes` (a locator) so the
peer can find a common ancestor efficiently. The locator is derived from the
local chain using exponentially spaced heights, capped by `MAX_LOCATOR_SIZE`.

---

## 4. Block synchronization

### 4.1 Goal

Download full blocks for the header chain that the node has decided to validate.

### 4.2 Flow

```
Local node                             Peer
   |                                    |
   |--- GET_BLOCKS([hash1, ...]) ------>|
   |                                    |
   |<----------- BLOCKS ----------------|
   |                                    |
   |     validate each block            |
   |     merkle root                    |
   |     registry root                  |
   |     transactions                   |
   |                                    |
   |  if valid: append to storage      |
```

### 4.3 Batching

Blocks are requested in batches. A single `GET_BLOCKS` may request up to
`MAX_BLOCKS_RESPONSE` hashes. The `max_total_bytes` field lets the requester
limit the total response size.

### 4.4 Ordering

A peer should return blocks in the order requested. The node validates them
sequentially. If any block in a batch is invalid, the entire batch is
considered untrusted from that peer for that request, but the node may still
retry the missing data from another peer.

### 4.5 Failure handling

- Invalid block: log, increment peer ban score, do not apply.
- Missing block: peer returns a shorter list; node may retry or request from
  another peer.
- Timeout: node marks request failed and retries.

---

## 5. State synchronization

### 5.1 Registry state

Registry state is **never** downloaded as a blob from a peer. It is recomputed
locally by replaying the governance transactions of the canonical chain.

This preserves the invariant:

```
registry_state = deterministic_replay(canonical_blocks)
```

A peer may send blocks, but the node builds its own registry state.

### 5.2 Monetary state

Not implemented. When added, monetary state will also be replayed locally from
canonical blocks.

### 5.3 Contract state

Not implemented. When added, contract state will also be replayed locally from
canonical blocks.

---

## 6. Archive object synchronization

### 6.1 Goal

Make content-addressed archive objects available locally.

### 6.2 Strategy

Archive objects are synchronized **lazily**:

1. A block or transaction references a content hash.
2. The node checks its local archive store.
3. If missing, it sends `GET_ARCHIVE(content_hash)` to a peer.
4. The peer returns the object if it has it.
5. The node validates the object hash matches the content hash.
6. The node stores the object locally.

### 6.3 Trust model

Archive objects are self-certifying by content hash. A peer cannot forge an
object for a given hash. However, a peer may claim to have an object it does
not have, or send the wrong object. The node verifies every byte.

---

## 7. Inventory and announcement

### 7.1 INV messages

A peer announces available items:

- `headers` — new block headers the peer knows about
- `blocks` — full blocks the peer has
- `archive` — archive objects the peer has
- `transactions` — transactions the peer has seen (not implemented in V1)

### 7.2 GET_DATA

After receiving an `INV`, the node may request specific items with `GET_DATA`.
The node decides which items to request based on local need and validation
priority.

### 7.3 No blind relay

A node does not relay blocks, headers, or transactions to other peers until
it has validated them itself. This prevents a malicious peer from using the
node to amplify invalid data.

---

## 8. Reorg handling during sync

If, during sync, a peer header chain has more accumulated work than the local
canonical chain:

1. The node downloads the full blocks for that chain.
2. It validates every block.
3. It uses the existing `ReorgEngine` to evaluate the candidate.
4. Only if the candidate has strictly more accumulated valid work does the
   node call `atomic_tip_switch`.
5. The storage backend handles atomicity and recovery.

Reorgs are therefore not a special networking case. They use the same
Phase 7H/7I path as locally detected forks.

---

## 9. Sync limits

| Limit | Value | Rationale |
|-------|-------|-----------|
| `MAX_HEADERS_RESPONSE` | 2000 | header-only messages stay small |
| `MAX_BLOCKS_RESPONSE` | 32 | bounded bandwidth per request |
| `MAX_LOCATOR_SIZE` | 32 | enough for very long chains |
| `MAX_INVENTORY_ENTRIES` | 5000 | prevents giant INV spam |
| `MAX_ARCHIVE_BYTES` | 2_000_000 | same as general payload limit |

---

## 10. Consensus boundary

The sync layer may:

- request data from peers
- validate data using Protocol V2
- store valid data
- announce local data to peers after validation

The sync layer may not:

- relax any Protocol V2 rule
- accept a chain because a peer says so
- apply state transitions from unvalidated data
- modify the genesis hash or network ID
