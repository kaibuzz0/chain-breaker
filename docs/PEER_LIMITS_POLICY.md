# Peer Limits Policy

Version: `chainbreaker-net-v1`  
Status: **architecture specification — no implementation yet**

---

## 1. Principle

All resource limits are **enforced before allocation**. A peer must not be able
to cause the local node to allocate unbounded memory, CPU, disk, or bandwidth.

---

## 2. Wire-level limits

| Limit | Value | Enforcement point |
|-------|-------|-------------------|
| `MAX_PAYLOAD_BYTES` | 2_000_000 (2 MiB) | after reading 4-byte payload length, before reading payload |
| `MAX_NETWORK_ID_LENGTH` | 64 bytes | after reading network ID length byte |
| `MAX_MESSAGE_SIZE` | `header + MAX_PAYLOAD_BYTES` | computed, never exceeded |
| `MAX_HEADERS_RESPONSE` | 2000 | in `HEADERS` payload validation |
| `MAX_BLOCKS_RESPONSE` | 32 | in `BLOCKS` payload validation |
| `MAX_INVENTORY_ENTRIES` | 5000 | in `INV` payload validation |
| `MAX_LOCATOR_SIZE` | 32 | in `GET_HEADERS` payload validation |

---

## 3. Connection-level limits

| Limit | Default | Notes |
|-------|---------|-------|
| `MAX_CONNECTIONS` | 125 | total inbound + outbound |
| `MAX_INBOUND_CONNECTIONS` | 87 | 70% of total |
| `MAX_OUTBOUND_CONNECTIONS` | 38 | 30% of total |
| `MAX_CONNECTIONS_PER_IP` | 5 | prevents single-host flooding |
| `HANDSHAKE_TIMEOUT_SECONDS` | 10 | time to complete HELLO/HELLO_ACK |
| `MESSAGE_READ_TIMEOUT_SECONDS` | 30 | time to read one full message |
| `IDLE_TIMEOUT_SECONDS` | 300 | no traffic allowed after handshake |
| `MAX_PENDING_REQUESTS_PER_PEER` | 16 | prevents request queue bloat |
| `MAX_OUTSTANDING_BYTES_PER_PEER` | 8_388_608 (8 MiB) | pending responses |

---

## 4. Rate limits

| Operation | Per-peer rate | Purpose |
|-----------|---------------|---------|
| `GET_HEADERS` | 1 per 2 seconds | prevents header spam |
| `GET_BLOCKS` | 1 per 5 seconds | prevents bandwidth abuse |
| `GET_ARCHIVE` | 1 per 1 second | archive objects may be large |
| `INV` | 1 per second | prevents announcement spam |
| `GET_DATA` | 2 per second | limits follow-up requests |

Burst allowances may be permitted but are bounded by memory budgets.

---

## 5. Memory budgets

| Resource | Per-peer budget | Global budget |
|----------|-----------------|---------------|
| read buffer | 8 KiB before handshake, 64 KiB after | — |
| pending requests | 16 | — |
| outstanding bytes | 8 MiB | `MAX_OUTSTANDING_BYTES_TOTAL` |
| message queue | 128 messages | `MAX_MESSAGE_QUEUE_TOTAL` |
| orphan blocks | 1024 | `MAX_ORPHAN_BLOCKS` |
| archive cache | 64 MiB | `MAX_ARCHIVE_CACHE_BYTES` |

---

## 6. Ban score policy

Peers accumulate ban score for protocol violations. Score thresholds:

| Violation | Score | Action |
|-----------|-------|--------|
| magic mismatch | 10 | disconnect |
| wrong network ID | 100 | disconnect + temporary ban |
| wrong genesis hash | 100 | disconnect + temporary ban |
| payload length too large | 50 | disconnect |
| payload hash mismatch | 50 | disconnect |
| invalid message type | 25 | disconnect |
| oversized typed payload | 25 | disconnect |
| timeout | 10 | increment, disconnect at threshold |
| repeated invalid blocks | 50 per block | disconnect + longer ban |
| request rate exceeded | 5 | throttle, disconnect at threshold |

**Thresholds:**
- `BAN_SCORE_DISCONNECT` = 100
- `BAN_SCORE_TEMP_BAN` = 100
- `BAN_SCORE_LONG_BAN` = 200

Temporary bans last 24 hours by default. Long bans are permanent until manual
operator intervention.

---

## 7. Local policy overrides

Operators may configure stricter limits than the defaults. They may not
configure limits that violate Protocol V2 consensus rules (for example, they
cannot lower `MAX_HEADERS_RESPONSE` below the minimum needed for sync, but the
spec defines a safe default).

---

## 8. Why limits are architecture

This document defines the limit values and the policy for enforcing them. The
exact implementation (whether in a connection handler, a rate-limiting
module, or a global resource guard) is a later engineering decision, but the
numbers and rules must be designed now so that Phase 8B implementation has a
contract to follow.
