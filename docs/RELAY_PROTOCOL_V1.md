# Relay Protocol V1

Version: `chainbreaker-net-v1`  
Status: **Phase 8J design document — architecture/specification only**

---

## 1. Purpose

This document specifies the protocol behavior for block relay messages in
Chain-Breaker Protocol V1.

---

## 2. Message semantics

### 2.1 `INV_BLOCK`

Payload:

```json
{
  "type": "block",
  "hashes": ["hash1", "hash2", ...]
}
```

Rules:

- Maximum 256 hashes per message.
- Hashes are hex strings of length 64.
- A node should not send an `INV_BLOCK` for a block it has not validated.
- A receiving node checks its duplicate cache before responding.

### 2.2 `GET_BLOCK`

Payload (existing Phase 8B format):

```json
{
  "hashes": ["hash1"],
  "max_total_bytes": 2000000
}
```

Rules:

- One or more hashes.
- `max_total_bytes` is a hint to limit response size.
- A peer may ignore the request if it does not have the block.
- A peer must not invent blocks.

### 2.3 `BLOCK`

Payload (existing Phase 8B format):

```json
{
  "blocks": [
    {"hash": "hash1", "block_bytes": "..."}
  ]
}
```

Rules:

- Maximum `MAX_BLOCKS_RESPONSE` blocks per message (32).
- Blocks must match requested hashes.
- Receiving node validates each block independently.

### 2.4 `REJECT_BLOCK`

Payload:

```json
{
  "hash": "hash1",
  "reason": "invalid-pow | bad-prev-hash | consensus-failure | unexpected"
}
```

Rules:

- Sent only after local validation fails.
- Optional; a node may silently drop invalid blocks instead.
- Must not be used as an authoritative network signal.

---

## 3. Request/response flow

```text
A --INV_BLOCK(hashX)--------> B
B --GET_BLOCK(hashX)-------> A
A --BLOCK(hashX)-----------> B
B validates
B --INV_BLOCK(hashX)-------> C, D (fanout)
C --GET_BLOCK(hashX)-------> B
B --BLOCK(hashX)-----------> C
```

---

## 4. Duplicate handling

Every node maintains a `RelaySeenCache`:

- Keys: block hash.
- Value: timestamp of first seen.
- Expiry: 2 hours.
- Maximum entries: 50,000.

Behavior:

- Before sending `INV_BLOCK`, check cache. If seen, do not announce.
- Before sending `GET_BLOCK`, check cache. If seen, do not request.
- On receiving a block, add to cache.

---

## 5. Orphan request policy

When an orphan arrives:

1. Add to orphan pool if space available.
2. If parent hash is unknown, send `GET_BLOCK(parent_hash)` to the peer that
   provided the orphan.
3. Limit parent requests to 1 per orphan.
4. If parent does not arrive within timeout, evict orphan.

---

## 6. Timeout behavior

| Operation | Timeout | Action |
|-----------|---------|--------|
| `GET_BLOCK` response | 30 seconds | retry with another peer |
| Orphan parent request | 60 seconds | evict orphan |
| Duplicate cache entry | 2 hours | evict |

---

## 7. Malformed request handling

A malformed relay message is rejected at the envelope/message layer:

- Invalid JSON → parser error, peer penalized.
- Bad hash format → `REJECT_BLOCK` or silent drop.
- Oversized inventory → truncate or reject entire message.
- Unknown message type → ignore.

---

## 8. Rate limits

- Maximum `INV_BLOCK` messages per peer per minute: 60.
- Maximum `GET_BLOCK` requests per peer per minute: 120.
- Maximum relay bytes per peer per minute: 10 MiB.
- Global relay byte budget: 50 MiB per minute.

Exceeding limits triggers score penalties and possible short-term bans.
