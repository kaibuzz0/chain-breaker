# Chain-Breaker Network Protocol V1

Version: `chainbreaker-net-v1`  
Status: **architecture specification — no implementation yet**  
Network protocol layer: **outer subsystem**  
Consensus dependency: **none. Networking transports consensus; it does not define it.**

---

## 1. Purpose

This document defines the wire protocol that Chain-Breaker nodes will use to
communicate with peers. It is deliberately a transport layer. It carries
consensus-critical data, but it may not add, remove, or alter any Protocol V2
consensus rule.

The network protocol is the **outermost** layer of the system. The consensus
core must be buildable and testable without any networking code.

---

## 2. Design principles

1. **Network is untrusted.** Every byte from a peer is treated as potentially
   hostile until validated against Protocol V2 rules.
2. **Network never decides consensus.** Peers may propose, never enforce.
3. **Fail static.** A malformed message, a timeout, or a protocol violation must
   never crash or corrupt local state.
4. **Resource limits first.** All byte and count limits are enforced before
   memory allocation.
5. **Consensus core has no socket dependency.** The network layer is allowed to
   call consensus validation; the consensus layer must never call networking.

---

## 3. Message envelope V1

Every message on the wire uses the following fixed-size header followed by a
variable payload.

| Field | Offset | Size | Type | Encoding | Validation |
|-------|--------|------|------|----------|------------|
| Magic | 0 | 4 | bytes | fixed `0x43 0x42 0x4E 0x31` (`"CBN1"`) | must equal magic, or close connection |
| Protocol version | 4 | 2 | uint16 | big-endian | must equal `1`; otherwise reject message |
| Network ID length | 6 | 1 | uint8 | raw | must equal `len(network_id_bytes)`, max `64` |
| Network ID | 7 | N | bytes | UTF-8, length from previous field | must equal configured network ID |
| Message type | 7+N | 1 | uint8 | raw | must be a known type; otherwise reject |
| Flags | 8+N | 1 | uint8 | raw | bit field; unknown required bits reject message |
| Payload length | 9+N | 4 | uint32 | big-endian | must be `<= MAX_PAYLOAD_BYTES` |
| Payload hash | 13+N | 32 | bytes | SHA-256 of payload | must match recomputed hash |
| Payload | 45+N | L | bytes | opaque to transport | passed to typed handler |

**Header length (minimum, with 22-byte network ID):** `67` bytes.  
**Maximum network ID length:** `64` bytes.  
**Maximum payload length (`MAX_PAYLOAD_BYTES`):** `2_000_000` bytes (2 MiB).  
**Maximum total message size:** `header + MAX_PAYLOAD_BYTES` = `2_000_109` bytes
(using the 22-byte network ID `chainbreaker-scripture-v2`).

### 3.1 Magic value

The magic identifies the network protocol family. It is **not** a security
field; it only prevents accidental cross-network connections.

```
CBN1_MAGIC = bytes([0x43, 0x42, 0x4E, 0x31])
```

### 3.2 Protocol version

```
NET_PROTOCOL_VERSION = 1
```

This is the version of the **wire protocol**, not the consensus protocol. A
peer that advertises a different wire version is rejected; a future version may
negotiate, but V1 does not.

### 3.3 Network ID

The network ID is the same string used in Protocol V2:
`"chainbreaker-scripture-v2"` (22 bytes UTF-8).

A mismatching network ID causes immediate connection termination.

### 3.4 Message types

| Type | Name | Direction | Purpose |
|------|------|-----------|---------|
| 0x01 | HELLO | both | initial handshake |
| 0x02 | HELLO_ACK | both | handshake response |
| 0x03 | PING | both | keep-alive / latency |
| 0x04 | PONG | both | keep-alive response |
| 0x05 | GET_HEADERS | requester | request header chain segment |
| 0x06 | HEADERS | responder | batch of block headers |
| 0x07 | GET_BLOCKS | requester | request full blocks by hash |
| 0x08 | BLOCKS | responder | batch of full blocks |
| 0x09 | GET_ARCHIVE | requester | request archive object by content hash |
| 0x0A | ARCHIVE | responder | archive object payload |
| 0x0B | INV | both | inventory announcement (hashes available) |
| 0x0C | GET_DATA | requester | request items from an INV |
| 0x0D | REJECT | both | protocol-level rejection notice |
| 0x00, 0x0E-0xFF | reserved | — | unknown type → reject message and peer |

### 3.5 Flags

Bit flags in the envelope:

| Bit | Name | Meaning |
|-----|------|---------|
| 0 | REQUIRES_ACK | sender expects an explicit response |
| 1 | COMPRESSED | payload is zlib-compressed (not implemented in V1) |
| 2-7 | reserved | must be zero in V1 |

Unknown required (bit 0 set where not expected) or unknown set reserved bits
must cause rejection.

### 3.6 Payload hash

`SHA-256(payload)`. Verified by recomputing over the exact payload bytes after
length enforcement. Hash mismatch → reject message and peer.

### 3.7 Failure behavior

Any envelope validation failure must:

1. Discard the message.
2. Record a protocol violation for the peer.
3. Optionally increment a per-peer ban score.
4. **Never** propagate the message to the consensus engine.

Repeated violations from the same peer may lead to disconnection.

---

## 4. Typed message payloads

All payloads are canonical JSON. Binary fields (hashes, block bytes) are hex
encoded. Future versions may add a binary payload encoding, but V1 uses JSON
to maximize cross-language inspectability.

### 4.1 HELLO / HELLO_ACK

```json
{
  "protocol_version": 1,
  "network_id": "chainbreaker-scripture-v2",
  "genesis_hash": "0000...",
  "best_height": 12345,
  "best_chain_work": "0000...",
  "feature_bits": [],
  "node_limits": {
    "max_payload_bytes": 2000000,
    "max_headers_response": 2000,
    "max_blocks_response": 32
  }
}
```

Validation:
- `protocol_version` must equal `1`.
- `network_id` must equal configured network ID.
- `genesis_hash` must equal configured genesis hash.
- `best_height` must be a non-negative integer.
- `best_chain_work` must be a 64-character hex string representing a 256-bit
  integer.
- `feature_bits` must be a list of known strings; unknown bits are ignored.
- `node_limits` values are informational; a node may enforce its own limits.

### 4.2 PING / PONG

```json
{"nonce": 1234567890}
```

PONG echoes the nonce.

### 4.3 GET_HEADERS

```json
{
  "start_hashes": ["0000...", "0000..."],
  "stop_hash": "0000...",
  "max_count": 500
}
```

Validation:
- `start_hashes` length must be `<= 32`.
- each hash must be 64 hex characters.
- `max_count` must be `<= MAX_HEADERS_RESPONSE` (2000).

### 4.4 HEADERS

```json
{
  "headers": [
    {"height": 100, "hash": "0000...", "header_bytes": "020000..."},
    ...
  ]
}
```

Validation:
- `headers` length must be `<= MAX_HEADERS_RESPONSE`.
- each entry contains valid hex of expected size for a V2 header.

### 4.5 GET_BLOCKS

```json
{
  "hashes": ["0000...", ...],
  "max_total_bytes": 1048576
}
```

Validation:
- `hashes` length `<= MAX_BLOCKS_RESPONSE` (32).
- each hash 64 hex chars.

### 4.6 BLOCKS

```json
{
  "blocks": [
    {"hash": "0000...", "block_bytes": "020000..."},
    ...
  ]
}
```

Validation:
- `blocks` length `<= MAX_BLOCKS_RESPONSE`.
- each `block_bytes` is valid hex encoding a `BlockV2`.

### 4.7 INV

```json
{
  "type": "headers",
  "hashes": ["0000...", ...]
}
```

Validation:
- `type` in `{"headers", "blocks", "archive", "transactions"}`.
- `hashes` length `<= MAX_INVENTORY_ENTRIES` (5000).

### 4.8 GET_DATA

```json
{
  "type": "headers",
  "hashes": ["0000...", ...]
}
```

Same limits as INV.

### 4.9 GET_ARCHIVE / ARCHIVE

```json
{"content_hash": "0000..."}
```

Archive payload is returned as raw bytes in the `ARCHIVE` payload; the envelope
payload length still governs maximum size.

### 4.10 REJECT

```json
{
  "code": "too-large",
  "reason": "payload exceeded limit",
  "offending_message_type": 8
}
```

Reject codes are advisory and must not cause the receiving node to change
consensus state.

---

## 5. Connection lifecycle

1. TCP connection established (future; not in this spec).
2. Each side sends HELLO.
3. Each side sends HELLO_ACK after validating peer HELLO.
4. After handshake, normal messages flow.
5. Either side may close the connection at any time.
6. A peer that sends an invalid HELLO is disconnected immediately.

---

## 6. Serialization rules

- All JSON is canonical (keys sorted, no extra whitespace, UTF-8).
- Hex strings are lowercase.
- Integers are decimal JSON numbers.
- No floating-point values.

---

## 7. Non-goals for V1

The following are explicitly **not** part of Network Protocol V1:

- peer discovery / address gossip
- NAT traversal
- transport encryption (TLS/Noise)
- mempool relay policy
- transaction fee market
- block template distribution
- light client protocol
- payment channel protocol

These may be defined in later network protocol versions or separate specs.

---

## 8. Consensus boundary

This document defines how data moves between peers. It does not define:

- what makes a block valid
- what makes a transaction valid
- which chain is canonical
- how registry state transitions
- how archive provenance is interpreted

Those rules remain in Protocol V2 and must be validated by the consensus core
independent of any network message.
