# Chain Sync Security Review

Version: `chainbreaker-net-v1`  
Status: **Phase 8I — chain sync implementation review**

---

## 1. Scope

This review covers the first chain synchronization implementation added in
Phase 8I:

- `chainbreaker/network/sync/` package
- `chainbreaker/network/constants.py` additions for sync defaults
- `chainbreaker/network/__init__.py` sync exports
- Tests under `tests/network/sync/`

It does not cover mempool, transaction relay, block relay gossip, or public
node operation.

---

## 2. Design principle preserved

```text
Peer:       "I have data."
Sync:       "I can request data."
Consensus:  "This data is valid or invalid."
Reorg:      "This valid chain has greater accumulated work."
Storage:    "Commit the accepted state."
```

The sync engine is a courier:

- It builds a header locator.
- It requests headers and blocks.
- It validates wire format.
- It delegates all consensus validation to `Ledger.add_block_v2()`.
- It delegates work comparison to `Ledger.chain_work()`.
- It delegates storage commit to `StorageBackend.append_block()`.

The sync engine never selects a canonical chain on its own.

---

## 3. Threat mitigations

### 3.1 Fake high-work chain

**Mitigation:**
- Peer work claims are ignored.
- Work is computed from headers that have already passed PoW validation.
- The response must exceed the local chain work before blocks are requested.

### 3.2 Invalid header flooding

**Mitigation:**
- Headers are parsed from fixed wire format.
- Each header is checked for `prev_hash`, target, PoW, and version.
- First invalid header aborts the response.
- The state machine transitions to `INVALID_DATA`.

### 3.3 Invalid block flooding

**Mitigation:**
- Blocks are requested only for validated header chains with more work.
- Each block is decoded and checked against expected prev_hash and target.
- Full ledger validation rejects invalid state transitions.
- Invalid blocks do not reach storage.

### 3.4 Out-of-order / duplicate blocks

**Mitigation:**
- Blocks are consumed in strict ascending order.
- `next_block_request()` returns the hash of the next pending header.
- A block that does not match the expected prev_hash is rejected.

### 3.5 Storage failure mid-sync

**Mitigation:**
- `_commit()` is a separate phase after full validation.
- Storage errors raise `SyncStorageError` and set `STORAGE_FAILURE` state.
- Pending block cache is cleared in `finally`.
- No partial commit is left in memory.

### 3.6 Wire format abuse

**Mitigation:**
- Reuses Phase 8B envelope parsing and message schema validation.
- `HeadersMessage` and `BlockMessage` enforce count and hash format.
- Decode failures raise `SyncInvalidDataError`.

### 3.7 Lower-work chain

**Mitigation:**
- Header chains with `new_work <= local_work` are rejected.
- No blocks are downloaded for inferior or equal-work chains.

---

## 4. Limitations

Phase 8I is a sequential, single-peer sync engine. It does not yet implement:

- timeouts
- retries
- multi-peer parallelism
- peer scoring hooks
- inventory-driven block announcements
- reorg during active sync race handling
- adversarial peer rotation

These are deferred to future phases.

---

## 5. Consensus boundary

Sync imports from:

- `chainbreaker.block` for data structures
- `chainbreaker.chain` for ledger validation and block encoding
- `chainbreaker.storage` for durable commit

It does not modify:

- `chainbreaker/block.py`
- `chainbreaker/consensus/protocol_v2.py` (not present as a module)
- frozen test vectors
- registry/archive/governance logic

Protocol V2 remains frozen.
