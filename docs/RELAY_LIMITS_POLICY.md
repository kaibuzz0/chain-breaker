# Relay Limits Policy

Version: `chainbreaker-net-v1`  
Status: **Phase 8J design document — architecture/specification only**

---

## 1. Purpose

This document specifies the resource limits that protect block relay from
abuse.

---

## 2. Inventory limits

| Limit | Value |
|-------|-------|
| `MAX_INV_BLOCK_HASHES` | 256 |
| `INV_BLOCK_RATE_PER_PEER` | 60 per minute |
| `INV_BLOCK_BURST` | 10 |

---

## 3. Request limits

| Limit | Value |
|-------|-------|
| `GET_BLOCK_RATE_PER_PEER` | 120 per minute |
| `GET_BLOCK_BURST` | 16 |
| `MAX_GET_BLOCK_HASHES` | 32 |
| `MAX_OUTSTANDING_GET_BLOCK` | 64 per peer |

---

## 4. Response limits

| Limit | Value |
|-------|-------|
| `MAX_BLOCKS_RESPONSE` | 32 |
| `MAX_BLOCK_BYTES_TOTAL` | 2 MiB per response |
| `BLOCK_RESPONSE_TIMEOUT` | 30 seconds |
| `MAX_BLOCK_RETRIES` | 3 |

---

## 5. Duplicate cache limits

| Limit | Value |
|-------|-------|
| `RELAY_SEEN_CACHE_SIZE` | 50,000 entries |
| `RELAY_SEEN_CACHE_TTL` | 2 hours |

---

## 6. Orphan pool limits

| Limit | Value |
|-------|-------|
| `MAX_ORPHAN_BLOCKS` | 1024 |
| `ORPHAN_MAX_AGE` | 2 hours |
| `ORPHAN_PARENT_REQUEST_TIMEOUT` | 60 seconds |
| `MAX_ORPHAN_PARENT_REQUESTS` | 1 per orphan |

---

## 7. Bandwidth limits

| Limit | Value |
|-------|-------|
| `RELAY_BYTES_PER_PEER_PER_MINUTE` | 10 MiB |
| `RELAY_BYTES_GLOBAL_PER_MINUTE` | 50 MiB |

---

## 8. Peer scoring impact

| Event | Score change |
|-------|--------------|
| Valid block relay | +10 |
| Invalid block | −150 |
| Orphan that later connects | +5 |
| Orphan flood | −50 |
| Exceeding rate limits | −75 |
| Timed-out block request | −30 |
| Malformed relay message | −100 |

---

## 9. Recovery rules

- Rate-limit violations trigger a 5-minute cool-down.
- Repeated violations within 1 hour lead to a 1-hour ban.
- Score recovery follows the model in `docs/PEER_SCORING_MODEL.md`.
