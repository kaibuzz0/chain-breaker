# Network Transport Threat Model

Version: `chainbreaker-net-v1`  
Status: **architecture specification — transport foundation phase**

---

## 1. Scope

This document covers threats introduced by the **transport** layer: the
movement of validated network messages between endpoints. Threats at the
parser/serialization layer are documented in `NETWORK_THREAT_MODEL.md`.

The transport layer does not validate message content. It only enforces:

- connection lifecycle
- queue bounds
- rate limits
- timeouts
- backpressure
- disconnect rules

---

## 2. Threats

### 2.1 Connection exhaustion

**Threat:** An adversary opens many transport connections to consume slots,
file descriptors, memory, or CPU.

**Mitigation:**
- `TransportLimits` defines `MAX_CONNECTIONS` (enforced by future connection manager).
- Separate inbound/outbound quotas.
- Per-IP connection limits.
- In-memory transport pair creation is operator-controlled and not exposed to
  arbitrary peers.

**Limitation:** This phase implements only the abstraction and the in-memory
pair. The connection manager comes later.

### 2.2 Queue flooding

**Threat:** A fast sender fills the inbound queue faster than the consumer can
process messages, causing unbounded memory growth.

**Mitigation:**
- `BoundedMessageQueue` enforces both message-count and byte-count limits.
- `put()` blocks with a timeout when the queue is full (backpressure).
- Exceeded limits raise `TransportLimitError`, which the caller may map to a
  disconnect.

### 2.3 Slow consumer

**Threat:** A receiver reads very slowly while the sender continues producing.

**Mitigation:**
- Backpressure propagates from the inbound queue to the sender's outbound queue.
- `send()` times out if the peer's inbound queue does not drain.
- Persistent slow consumers are disconnected by policy (enforcement in future
  manager).

### 2.4 Resource starvation

**Threat:** A single connection monopolizes bandwidth, memory, or CPU.

**Mitigation:**
- `RateLimiter` bounds messages and bytes per time window.
- Per-connection queue byte limits.
- Global limits enforced by the future connection manager.

### 2.5 Timeout abuse

**Threat:** A peer keeps connections open with minimal traffic to avoid idle
disconnect while consuming resources.

**Mitigation:**
- `idle_timeout_seconds` in `TransportLimits`.
- `MemoryTransport.check_idle()` exposes the idle state for the manager to act on.
- Handshake, send, and receive timeouts are bounded.

### 2.6 Connection churn

**Threat:** An adversary repeatedly connects and disconnects to exhaust
connection-state resources.

**Mitigation:**
- Connection objects are lightweight.
- Rate limits apply to message flow, not just connection count.
- Future manager will enforce per-peer reconnect limits.

### 2.7 Bandwidth abuse

**Threat:** A peer sends or requests large volumes of data.

**Mitigation:**
- `max_bytes_per_window` rate limit.
- `max_outbound_queue_bytes` caps outstanding data.
- No response larger than `MAX_PAYLOAD_BYTES` is ever serialized.

---

## 3. Transport-layer guarantees

1. **No allocation before validation.** The transport layer only moves bytes
   that have already passed envelope parsing.
2. **Bounded queues.** Every queue has hard depth and byte limits.
3. **Bounded waits.** Every blocking operation has a timeout.
4. **Fail closed.** When a limit is hit, the operation fails rather than
   silently buffering.
5. **No consensus dependency.** Transport code does not import ledger, storage,
   registry, archive, or governance modules.

---

## 4. Interaction with parser layer

```
[peer bytes]
    |
    v
[parser]     <-- NETWORK_THREAT_MODEL.md
    |
    v
[validated envelope]
    |
    v
[transport queue]   <-- this document
    |
    v
[message handler]   <-- future phase
    |
    v
[consensus engine]  <-- never touched by transport
```

---

## 5. Remaining limitations

The following are out of scope for Phase 8C and will be addressed later:

- actual TCP/UDP sockets
- peer identity and authentication
- encryption
- NAT traversal
- peer discovery
- connection manager / global limits
- reputation / ban score enforcement
- DoS protection at the network edge

These limitations are documented so they are addressed deliberately.
