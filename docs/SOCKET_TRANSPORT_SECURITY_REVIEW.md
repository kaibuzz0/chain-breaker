# Socket Transport Security Review

Version: `chainbreaker-net-v1`  
Status: **security review for Phase 8E — real TCP socket transport**

---

## 1. Scope

This document reviews the socket transport layer introduced in Phase 8E. It
covers the files under `chainbreaker/network/socket/` and the tests under
`tests/network/socket/`.

Phase 8E is the first phase that uses real networking, but it intentionally
remains narrow:

- Allowed: TCP socket abstraction, connect/listen lifecycle, stream framing,
  send/receive bytes, integration with existing Transport interface.
- Forbidden: peer discovery, gossip, synchronization, block relay,
  transaction relay, mempool, public node operation, consensus changes.

---

## 2. Threats and Mitigations

### 2.1 Connection flooding / socket exhaustion

**Threat:** An adversary opens many TCP connections to exhaust file
descriptors or accept queue slots.

**Mitigation:**
- The server is not yet a public listener; tests use `asyncio.start_server`
  with ephemeral ports and a fixed listen backlog (`listen_backlog=128`).
- Future phases will add an explicit connection manager on top of the socket
  transport to enforce `max_connections`.
- Each accepted socket is wrapped in `TCPServerTransport` and closed on error.

### 2.2 Half-open connections

**Threat:** A peer opens a connection but never sends or completes a handshake,
leaving resources tied up.

**Mitigation:**
- `TCPClientTransport` and `TCPServerTransport` use `asyncio.wait_for` with
  `read_timeout_seconds` on every `receive()` call.
- `connect_timeout_seconds` bounds the initial TCP connect.
- Future phases will layer idle timeout and keep-alive policies.

### 2.3 Slow clients / slowloris

**Threat:** A peer sends bytes very slowly to keep a connection open and
consume memory.

**Mitigation:**
- Reads are bounded by `read_timeout_seconds`.
- The framing accumulator is bounded by `max_frame_buffer_bytes`.
- A declared payload length larger than `max_message_size` is rejected before
  the payload bytes are accumulated.

### 2.4 Oversized messages

**Threat:** A peer declares a huge payload length to force large allocation.

**Mitigation:**
- `EnvelopeFraming._try_parse_one()` reads the payload length from the fixed
  header and checks it against `SocketLimits.max_message_size` before
  allocating or accepting the payload bytes.
- `SocketConnection.send_all()` rejects sends larger than `max_message_size`.

### 2.5 Partial reads and split packets

**Threat:** TCP does not preserve message boundaries; packets may be split,
combined, or delivered out of order relative to application boundaries.

**Mitigation:**
- `EnvelopeFraming` maintains a persistent `bytearray` accumulator.
- It parses complete envelopes only when the fixed header and full payload are
  present.
- Multiple envelopes in a single read are returned in order.

### 2.6 Disconnect mid-frame

**Threat:** A peer sends a partial envelope and then disconnects.

**Mitigation:**
- `TCPClientTransport.receive()` and `TCPServerTransport.receive()` detect an
  empty read and raise `SocketClosedError`, triggering cleanup.
- The accumulator is discarded when the transport closes.

### 2.7 Malformed streams / garbage injection

**Threat:** Random or malicious bytes are inserted into the stream.

**Mitigation:**
- `EnvelopeFraming` scans for the magic bytes (`CBN1`) and drops leading
  garbage until it finds a valid header.
- `parse_envelope()` validates magic, protocol version, network ID, and payload
  hash; invalid frames raise `EnvelopeError`.

### 2.8 Partial writes

**Threat:** A socket send buffer is full and `send()` writes fewer bytes than
requested.

**Mitigation:**
- Asyncio `StreamWriter` handles buffering and backpressure; `drain()` is used
  with a write timeout.
- `SocketConnection.send_all()` (legacy raw-socket helper) loops until all bytes
  are sent or a timeout occurs.

### 2.9 Resource starvation

**Threat:** Memory or CPU consumed by framing, timers, or open sockets.

**Mitigation:**
- `max_frame_buffer_bytes` caps the accumulator.
- `max_message_size` caps each message.
- All socket I/O uses timeouts; no indefinite blocking reads/writes.

---

## 3. Limitations and future work

- No TLS or transport encryption yet.
- No public listening node or accept-rate limiting yet (deferred to peer
  networking phases).
- No idle/keep-alive timeouts yet.
- No per-IP or per-peer connection quotas yet.
- Ban list from Phase 8D is in-memory only.

---

## 4. Consensus boundary

The socket layer does not import or depend on:

- ledger
- storage
- registry
- archive
- governance
- consensus state

It only moves bytes, frames envelopes, and surfaces them to the existing
parser/transport/handshake layers.
