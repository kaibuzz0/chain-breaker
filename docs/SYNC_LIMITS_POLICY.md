# Sync Limits Policy

Version: `chainbreaker-net-v1`  
Status: **Phase 8H design document — architecture/specification only**

---

## 1. Purpose

This document specifies the resource limits that protect the sync subsystem
and the node from abuse. All limits are enforced before implementation in
Phase 8I.

---

## 2. Per-peer limits

| Limit | Default | Behavior on exceed |
|-------|---------|--------------------|
| `max_outstanding_header_requests` | 1 | reject new `GET_HEADERS` |
| `max_outstanding_block_requests` | 16 | reject new `GET_BLOCK` |
| `max_headers_per_second` | 5 | drop excess `HEADERS` |
| `max_blocks_per_second` | 8 | drop excess `BLOCK` |
| `max_sync_bytes_per_second` | 1 MiB | drop or throttle |
| `response_timeout_seconds` | 30 | retry with another peer |

---

## 3. Global limits

| Limit | Default |
|-------|---------|
| `max_total_outstanding_blocks` | 64 |
| `max_sync_memory_bytes` | 64 MiB |
| `max_block_download_queue` | 256 |
| `max_concurrent_sync_peers` | 3 |

---

## 4. Request timeout rules

- Each `GET_HEADERS` and `GET_BLOCK` request has a timeout.
- On timeout, the request is marked failed and retried up to `max_retries` (3).
- After retries are exhausted, the peer score is reduced.
- A peer with repeated timeouts is banned.

---

## 5. Retry policy

1. Retry the same request on the same peer once.
2. If that fails, retry on a different peer.
3. If multiple peers fail for the same hash/header, treat the data as
   unavailable and log the incident.
4. Do not retry infinitely.

---

## 6. Peer scoring impact

| Event | Score change |
|-------|--------------|
| Valid sync response | +5 |
| Timeout | −30 |
| Invalid header | −100 |
| Invalid block | −150 |
| Malformed sync message | −100 |
| Exceeding rate limits | −50 |
| Successful reorg via this peer | +20 |

Repeated failures lead to bans via the Phase 8G scoring model.

---

## 7. Memory limits

- Header response cache: max 2000 headers × 1 KB ≈ 2 MB.
- Block download cache: max 64 outstanding blocks × max block size.
- Sync queue: max 256 pending block hashes.
- Total sync memory is bounded by `max_sync_memory_bytes`.

When memory is exhausted, sync stalls new downloads until space is freed by
validation and commit.

---

## 8. Bandwidth controls

- Token buckets enforce per-peer and global byte limits.
- Large `BLOCK` responses count toward the byte budget.
- Sync traffic is separate from gossip traffic budgets.

---

## 9. Queue limits

- Download queue is FIFO with bounded size.
- If full, new blocks are not scheduled until queue drains.
- This prevents unbounded growth when validation is slower than download.
