# Header Sync Design

Version: `chainbreaker-net-v1`  
Status: **Phase 8H design document — architecture/specification only**

---

## 1. Purpose

This document defines header-first synchronization for Chain-Breaker.
Header-first means a node downloads and validates headers before requesting any
full blocks. This reduces bandwidth and exposes invalid chains early.

---

## 2. Why header-first

1. **Bandwidth efficiency.** Headers are small; full blocks may be large.
2. **Early rejection.** Invalid proof-of-work or broken adjacency is caught
   before block download.
3. **Deterministic work comparison.** Accumulated work can be computed from
   headers alone, allowing the reorg engine to decide before committing.
4. **Bounded state.** Header chains can be validated without writing to the
   main storage chain.

---

## 3. Locator strategy

A header locator is a sparse list of block hashes from the local best tip back
to genesis. It lets a peer find the most recent common ancestor without sending
the entire chain.

Locator construction:

```
hashes = []
step = 1
current = tip
while current != genesis and len(hashes) < MAX_LOCATOR_SIZE:
    hashes.append(hash_at_height(current))
    current = max(0, current - step)
    if len(hashes) > 10:
        step *= 2
hashes.append(genesis_hash)
```

Properties:
- Size bounded by `MAX_LOCATOR_SIZE` (32).
- Earlier heights are sampled exponentially sparsely.
- The local tip and genesis are always included.

---

## 4. `GET_HEADERS` request

A sync peer sends:

```json
{
  "locator": ["hash1", "hash2", ...],
  "stop_hash": "optional_hash",
  "max_results": 2000
}
```

The responder returns up to `max_results` headers following the first locator
hash it recognizes in the main chain.

---

## 5. `HEADERS` response validation

On receiving headers, the sync layer performs envelope validation and then
passes each header to consensus validation. Consensus checks:

- header hash meets target difficulty
- `previous_hash` links correctly
- timestamp rules (Protocol V2)
- version and size limits
- merkle root consistency

Any failure marks the entire response as invalid.

---

## 6. Accumulated-work comparison

After validating a header chain, the sync layer computes its total work:

```
chain_work = sum(difficulty_to_work(header.bits) for header in chain)
```

The reorg engine compares this to the local best chain work:

- If `chain_work <= local_work`, ignore the peer chain.
- If `chain_work > local_work`, request the corresponding blocks.

The sync layer does not decide the comparison; it only presents the candidate
to the reorg engine.

---

## 7. Fork detection

A fork is detected when a received header chain diverges from the local chain
at some common ancestor.

Response:

1. Validate the diverging headers independently.
2. If the fork chain has more work, download its blocks.
3. Let the reorg engine decide whether to activate the fork.
4. If the fork is shorter or invalid, discard it.

The sync layer must not activate a fork on its own.

---

## 8. Interaction with Phase 7 reorg engine

The reorg engine is the only component that may change the canonical chain.
Sync will invoke it with:

- a list of validated headers (for work comparison)
- the full validated blocks (for commit)

The reorg engine returns:

- `NO_CHANGE` — local chain remains best
- `REORG` — a rollback + forward sequence to apply
- `INVALID` — candidate rejected

Sync applies the returned operation to storage.

---

## 9. Invalid header handling

If a header fails validation:

1. Stop processing the response.
2. Penalize the peer (score reduction, possible ban).
3. Discard the partial chain.
4. Try the next sync peer.
5. Do not write anything to storage.

---

## 10. Checkpoint considerations

Phase 8H does not introduce consensus checkpoints. Future phases may add
checkpoints for eclipse resistance. If checkpoints are added:

- Sync must refuse to reorganize below a checkpoint.
- Checkpoints are a consensus-layer rule, not a sync-layer preference.
- Sync only enforces whatever rules consensus provides.

---

## 11. Memory and resource policy

- Header download responses are bounded to 2000 headers.
- Each header is small (≤ 1 KB); total response is bounded.
- Invalid headers are rejected before any block download is scheduled.
- Locator size is bounded to 32 hashes.
