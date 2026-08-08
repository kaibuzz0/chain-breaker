# Block Relay Security Review

Version: `chainbreaker-net-v1`  
Status: **Phase 8K — block relay implementation review**

---

## 1. Scope

This review covers the block relay implementation added in Phase 8K:

- `chainbreaker/network/relay/` package
- `chainbreaker/network/constants.py` additions for relay defaults
- Tests under `tests/network/relay/`

It does not cover transaction relay, mempool, fee logic, or mining
communication.

---

## 2. Design principle preserved

```text
Peer:       "I have a block."
Relay:      "I can announce and request blocks."
Consensus:  "This block is valid or invalid."
Reorg:      "This valid chain has more work."
Storage:    "Commit accepted state."
```

The relay layer:

- announces block hashes via `INV_BLOCK`
- requests blocks via `GET_BLOCK`
- delivers blocks via `BLOCK`
- validates every received block through the ledger before committing or
  relaying
- delegates storage commits to `StorageBackend.append_block()`

Relay never decides canonicality.

---

## 3. Threat mitigations

### 3.1 Block/announcement flooding

- `INV_BLOCK` size limited by `max_inv_items` (default 256).
- Per-peer inventory rate limits.
- Global and per-peer byte budgets.
- Invalid blocks are dropped and peer score impacted.

### 3.2 Duplicate amplification

- `RelaySeenCache` with bounded size and TTL.
- Cached hashes do not trigger new `GET_BLOCK` requests or announcements.

### 3.3 Invalid block injection

- Every `BLOCK` response is decoded and checked against its claimed hash.
- `Ledger.add_block_v2()` validates consensus rules.
- Invalid blocks do not reach storage and are not relayed.

### 3.4 Orphan flooding

- Orphan pool bounded to `max_orphan_blocks`.
- Orphan entries age out.
- Orphans are not relayed.

### 3.5 Unsolicited full blocks

- `BLOCK` responses are validated independently of whether they were
  requested.
- Hash mismatch causes immediate rejection.

### 3.6 Bandwidth exhaustion

- `MAX_BLOCKS_RESPONSE` limits blocks per response.
- `max_block_bytes_total` caps response size.
- Per-peer and global relay byte budgets.

### 3.7 Storage failure mid-relay

- Storage commit is a discrete step after successful validation.
- Exceptions are surfaced as `error` results, not silent commits.

---

## 4. Limitations

Phase 8K is a single-peer, sequential relay engine. Not yet implemented:

- actual transport send integration
- multi-peer fanout
- timeouts and retries driven by a scheduler
- orphan chain reconstruction beyond connection tracking
- peer scoring wiring
- compact blocks
- inventory batching across multiple peers

These are deferred to future phases.

---

## 5. Consensus boundary

Relay imports:

- `chainbreaker.block` for data structures
- `chainbreaker.chain` for ledger validation
- `chainbreaker.storage` for durable commit
- `chainbreaker.network.messages` for wire messages

It does not modify consensus rules, Protocol V2, or frozen vectors.
