# Peer Handshake Security Review

Version: `chainbreaker-net-v1`  
Status: **security review for Phase 8D — connection manager + handshake execution**

---

## 1. Scope

This document reviews the security of the peer handshake subsystem introduced in
Phase 8D. It covers:

- `chainbreaker/network/transport/handshake.py`
- `chainbreaker/network/transport/manager.py`
- tests in `tests/network/transport/test_handshake.py` and
  `tests/network/transport/test_connection_manager.py`

The review is limited to handshake execution over the abstract transport layer.
Sockets, discovery, synchronization, relay, and mempool functionality do not yet
exist.

---

## 2. Threats and Mitigations

### 2.1 Fake network identity

**Threat:** A peer claims to belong to the Chain-Breaker network by sending a
HELLO with the correct-looking fields but an incorrect `network_id`.

**Mitigation:**
- `HandshakeContext.validate_hello()` compares the peer's `network_id` against
  the local `network_id`.
- Mismatch causes immediate rejection (`REJECTED`) and a negative HELLO_ACK.
- The connection manager records the reject and eventually bans the peer key
  after repeated failures.

**Test coverage:**
- `test_handle_hello_wrong_network`
- `test_reject_wrong_network`

### 2.2 Fake genesis claims

**Threat:** A peer sends a HELLO claiming a different genesis hash, attempting
to join a different chain or fork.

**Mitigation:**
- `HandshakeContext.validate_hello()` compares the peer's `genesis_hash` against
  the local genesis hash.
- Mismatch causes immediate rejection.

**Test coverage:**
- `test_handle_hello_wrong_genesis`
- `test_reject_wrong_genesis`

### 2.3 Protocol version downgrade / upgrade

**Threat:** A peer advertises an unsupported protocol version, potentially
exploiting version-specific behavior or forcing a downgrade.

**Mitigation:**
- `HandshakeContext.validate_hello()` requires an exact match with
  `NET_PROTOCOL_VERSION`.
- There is no version negotiation: mismatch is a hard rejection.

**Test coverage:**
- `test_handle_hello_unsupported_version`
- `test_reject_unsupported_version`

### 2.4 Handshake flooding

**Threat:** An adversary opens many connections and sends HELLO messages
to consume CPU, memory, or connection slots.

**Mitigation:**
- `ConnectionManager` enforces `max_connections`.
- Each connection is lightweight and is closed on rejection.
- Rejected peers are tracked; three rejects from the same peer key result in a
  ban.

**Test coverage:**
- `test_connection_manager_capacity`
- `test_repeated_failed_handshake_bans_peer`

### 2.5 Repeated failed handshake attempts

**Threat:** A peer retries handshake failures indefinitely.

**Mitigation:**
- `ConnectionManager._record_reject()` increments a per-peer-key counter.
- After three rejects the peer key is added to `_banned_peers`.
- Future connection attempts from banned peer keys raise `TransportLimitError`
  before any handshake traffic is generated.

**Test coverage:**
- `test_repeated_failed_handshake_bans_peer`

### 2.6 Handshake timeout / slow peer

**Threat:** A peer opens a connection but never completes the handshake,
consuming a slot or causing indefinite waits.

**Mitigation:**
- The transport layer provides bounded `receive_timeout_seconds`.
- `ConnectionManager.accept()` and `register_inbound()` rely on transport receive
timeouts.
- On timeout the connection is closed and removed from the manager.

**Test coverage:**
- `test_handshake_timeout`

### 2.7 Invalid handshake ordering

**Threat:** A peer sends HELLO_ACK before HELLO, or sends messages out of the
expected order.

**Mitigation:**
- `HandshakeSession` maintains a strict state machine.
- `handle_hello_ack()` only accepts HELLO_ACK in `WAIT_HELLO_ACK` state.
- `handle_hello()` rejects HELLO in terminal or established states.

**Test coverage:**
- `test_hello_ack_without_hello_rejected`
- `test_unsolicited_hello_ack_when_waiting_for_hello`
- `test_handle_hello_in_wrong_state`

### 2.8 Capability abuse

**Threat:** A peer advertises capabilities it does not actually support, or
tries to force the node to enable unsupported features.

**Mitigation:**
- Capabilities are only the intersection of local and remote `feature_bits`.
- Capabilities are declarative; no behavior is enabled by a capability yet.
- Future phases will gate actual functionality behind these declared features.

**Test coverage:**
- `test_handle_valid_hello`
- `test_handle_hello_matching_features`

---

## 3. Remaining limitations

- Banned peers are tracked in memory only; persistence belongs to a future
  phase.
- There is no transport encryption or identity authentication yet.
- Peer keys are arbitrary strings supplied by the caller; real peer identity
  will come with sockets and cryptographic identities.
- Ban policy is simple count-based; no cooldown or decay.
- The connection manager does not yet handle background keep-alive or idle
  reaping.

---

## 4. Consensus boundary

The handshake subsystem does not import or depend on:

- ledger
- storage backend
- registry state
- archive
- governance
- consensus protocol V2

It only validates compatibility parameters (`network_id`, `genesis_hash`,
`protocol_version`) and negotiates feature declarations. Consensus-critical
decisions remain in the non-network core.
