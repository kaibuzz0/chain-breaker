# Peer Handshake Specification

Version: `chainbreaker-net-v1`  
Status: **architecture specification — no implementation yet**

---

## 1. Purpose

The handshake is the only point in the network protocol where a peer reveals
identity and capability information. It is also the primary boundary where
incompatible or malicious peers are rejected before they can influence local
state.

---

## 2. Handshake sequence

```
Initiator                              Responder
   |                                       |
   |----------- HELLO -------------------->|
   |                                       |
   |          validate HELLO               |
   |                                       |
   |<---------- HELLO_ACK -------------------|
   |                                       |
   |          validate HELLO_ACK           |
   |                                       |
   |----------- HELLO_ACK_ACK? (optional) ->|   [not used in V1]
   |                                       |
   |=========== normal traffic ===========|
```

Both sides send a HELLO message. After receiving and validating the peer's
HELLO, each side sends HELLO_ACK. There is no third round-trip in V1.

---

## 3. HELLO payload

```json
{
  "protocol_version": 1,
  "network_id": "chainbreaker-scripture-v2",
  "genesis_hash": "0000a6fd1e57aafd19da552440faa94803dbf1a1773bcd9af8ce3e0ae9fd13db",
  "best_height": 0,
  "best_chain_work": "0000000000000000000000000000000000000000000000000000000000000000",
  "feature_bits": [],
  "node_limits": {
    "max_payload_bytes": 2000000,
    "max_headers_response": 2000,
    "max_blocks_response": 32
  }
}
```

### 3.1 Required validation rules

| Field | Rule | Failure action |
|-------|------|----------------|
| `protocol_version` | must equal `1` | disconnect |
| `network_id` | must equal configured network ID | disconnect |
| `genesis_hash` | must equal configured genesis hash | disconnect |
| `best_height` | integer, `0 <= best_height <= 2^63-1` | disconnect |
| `best_chain_work` | 64 lowercase hex chars | disconnect |
| `feature_bits` | array of strings | ignore unknown |
| `node_limits` | object with integer values | ignore; local limits take precedence |

### 3.2 Why genesis hash is non-negotiable

A peer with the wrong genesis hash is on a different chain. There is no
recovery path. The connection is closed immediately.

A peer may not attempt to "convince" a node to change genesis. That is a
consensus constant, not a negotiation topic.

### 3.3 Chain work is advisory

`best_chain_work` is used by the sync layer to prioritize peers and detect
candidates with more work. It is **not** trusted. The local node validates all
headers itself.

---

## 4. HELLO_ACK payload

```json
{
  "protocol_version": 1,
  "network_id": "chainbreaker-scripture-v2",
  "genesis_hash": "0000a6fd1e57aafd19da552440faa94803dbf1a1773bcd9af8ce3e0ae9fd13db",
  "best_height": 12345,
  "best_chain_work": "0000000000000000000000000000000000000000000000000000000000000001",
  "feature_bits": [],
  "node_limits": {
    "max_payload_bytes": 2000000,
    "max_headers_response": 2000,
    "max_blocks_response": 32
  },
  "handshake_complete": true
}
```

The `handshake_complete` flag confirms the peer has accepted our HELLO.

---

## 5. Hard rejection conditions

A peer is disconnected immediately if its HELLO:

1. Uses an unsupported `protocol_version`.
2. Uses the wrong `network_id`.
3. Uses the wrong `genesis_hash`.
4. Provides a `best_height` that is negative, non-integer, or exceeds 2^63-1.
5. Provides a `best_chain_work` that is not 64 hex characters.
6. Repeats HELLO after handshake completion.
7. Sends any non-HELLO message before completing handshake.

---

## 6. Soft rejection conditions

The following may be logged but do not cause disconnection:

1. Unknown `feature_bits`.
2. `node_limits` that differ from local limits.
3. `best_chain_work` lower than expected (peer may be behind).
4. `best_height` inconsistent with `best_chain_work` (sync layer decides).

---

## 7. Peer identity

Network Protocol V1 does **not** establish a persistent peer identity.

There is:

- no node ID field
- no signature in the handshake
- no reputation state
- no peer database schema

Peer identity and reputation are explicitly deferred to a later phase.

This is intentional: identity is a hard distributed-systems problem that should
not be rushed.

---

## 8. Timing and timeouts

A handshake must complete within `HANDSHAKE_TIMEOUT_SECONDS` (recommended
value: `10`). If either side does not receive a valid HELLO/HELLO_ACK within
that window, the connection is closed.

---

## 9. Consensus boundary

The handshake may not:

- alter the local genesis hash
- alter the local network ID
- alter Protocol V2 rules
- select a canonical chain
- apply any state transition

It only determines whether the peer is speaking the same protocol on the same
network.
