# Block Sync Design

Version: `chainbreaker-net-v1`  
Status: **Phase 8H design document — architecture/specification only**

---

## 1. Purpose

This document defines how Chain-Breaker downloads and commits full blocks once
a better header chain has been identified.

---

## 2. Validation-before-storage rule

A block must pass full consensus validation before it is written to durable
storage or accepted as part of the canonical chain. Sync enforces this rule
by design:

```
Receive block
        |
        v
Validate block (consensus)
        |
        +-- invalid --> reject + penalize peer
        |
        +-- valid --> pass to reorg engine
                    |
                    v
              Decide activation
                    |
                    v
              Storage commit
```

Sync must never write an unvalidated block to the chain store.

---

## 3. Block request lifecycle

For each block hash in the better header chain:

1. Add hash to a bounded download queue.
2. Send `GET_BLOCK` to a selected sync peer.
3. Track outstanding request with timeout.
4. On `BLOCK` response, validate immediately.
5. If valid, store in a temporary validated-block cache (not main chain yet).
6. When the full segment is validated, present to reorg engine.
7. On reorg approval, commit to storage.

---

## 4. Parallel download possibilities

Phase 8H permits but does not require parallel block downloads.

Constraints if parallel:

- Preserve validation order so that transaction inputs exist when needed.
- Cap total outstanding bytes to prevent memory exhaustion.
- Track per-peer and global outstanding request counts.
- Do not commit out-of-order blocks to storage before the reorg decision.

A future phase may implement parallel pipelining; Phase 8I should start with
sequential downloads to minimize complexity.

---

## 5. Ordering constraints

Blocks must be downloaded and validated in ascending height order relative to
the common ancestor. This ensures:

- Each block’s `previous_hash` refers to a validated predecessor.
- State transitions can be applied incrementally.
- Reorg rollback/forward boundaries are well-defined.

---

## 6. Crash recovery interaction

The storage layer (Phase 7F) provides atomic commits and snapshots. Sync
relies on this behavior:

- If a node crashes during block download, it resumes from the last committed
  chain tip.
- Partially downloaded blocks are not trusted.
- In-flight download state is ephemeral and rebuilt from the committed tip.
- Sync never writes uncommitted intermediate state to storage.

---

## 7. Archive object handling

Archive objects (Phase 7I) are separate from the main chain. Sync may request
archive data only after the main chain is current, using `GET_ARCHIVE` and
`ARCHIVE` messages. Archive sync:

- does not affect canonical chain selection
- is optional for full-node operation
- must be rate-limited separately from block sync
- must validate archive integrity against registry references (future)

---

## 8. Invalid block handling

If a block fails validation:

1. Stop processing the segment.
2. Penalize the peer.
3. Discard the partial segment.
4. Re-request from another peer.
5. If multiple peers fail on the same hash, mark the header chain as
   suspect and restart header sync from a different peer.

---

## 9. Resource policy

- `MAX_BLOCKS_RESPONSE` limits blocks per response (32).
- Outstanding block requests are bounded per peer and globally.
- Downloaded blocks are cached only until the reorg decision.
- Memory usage is proportional to outstanding blocks × block size limit.
