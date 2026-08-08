# Phase 8C — Network Transport Foundation Report

## Status

**Transport abstraction and in-memory primitives complete.** No sockets, no
peer discovery, no sync, no relay, no consensus changes.

## Branch

- `phase8c-network-transport-foundation`
- Base: `phase8b-network-protocol-parser @ 4df5c29`

## Files added

| File | Purpose |
|------|---------|
| `chainbreaker/network/transport/__init__.py` | Public API |
| `chainbreaker/network/transport/interface.py` | Abstract `Transport` interface |
| `chainbreaker/network/transport/connection.py` | `ConnectionState` enum and `Connection` state machine |
| `chainbreaker/network/transport/queue.py` | `BoundedMessageQueue` with depth and byte limits |
| `chainbreaker/network/transport/limits.py` | `TransportLimits` and `RateLimiter` |
| `chainbreaker/network/transport/errors.py` | Transport exception hierarchy |
| `chainbreaker/network/transport/memory.py` | `MemoryTransport` and `create_memory_transport_pair` |
| `tests/network/transport/__init__.py` | Test package marker |
| `tests/network/transport/test_transport_interface.py` | Transport send/receive/close/status tests |
| `tests/network/transport/test_connection_state.py` | Connection lifecycle tests |
| `tests/network/transport/test_queue_limits.py` | Bounded queue tests |
| `tests/network/transport/test_rate_limits.py` | Sliding-window rate limiter tests |
| `tests/network/transport/test_memory_transport.py` | In-memory transport tests |
| `tests/network/transport/test_backpressure.py` | Backpressure and slow-consumer tests |
| `tests/network/transport/test_disconnect_rules.py` | Disconnection and state-error tests |
| `docs/NETWORK_TRANSPORT_THREAT_MODEL.md` | Transport-specific threat model |
| `docs/PHASE8C_TRANSPORT_FOUNDATION_REPORT.md` | This report |

## Design decisions

### Transport interface

`Transport` is an abstract class with `send`, `receive`, `close`, and `status`.
It operates on `NetworkEnvelope` objects. Concrete implementations supply byte
movement; the interface is independent of sockets.

### Connection state machine

```
CREATED -> OPENING -> ACTIVE -> DRAINING -> CLOSED
```

Invalid transitions raise `TransportStateError`. `ensure_open()` checks the
connection is usable before I/O.

### Bounded queues

`BoundedMessageQueue` enforces both message count and byte capacity. `put()`
blocks with a timeout; when the queue is full, the caller receives
`TransportLimitError`, enabling backpressure or disconnection.

### Rate limiting

`RateLimiter` maintains sliding windows of message timestamps and byte counts.
It rejects operations that would exceed `max_messages_per_window` or
`max_bytes_per_window`.

### Memory transport

`create_memory_transport_pair()` builds two `MemoryTransport` instances whose
queues are cross-wired. It is used to test the transport abstraction without
any network access.

### No consensus dependency

Transport code depends only on:

- `chainbreaker.network.envelope` and `chainbreaker.network.messages`
- `chainbreaker.crypto.HashEngine` (via envelope serialization)
- standard library (`asyncio`, `dataclasses`, `enum`, `time`, `collections`)

No imports from block, consensus, storage, registry, archive, governance, or
witness modules.

## Resource limits

| Limit | Default | Purpose |
|-------|---------|---------|
| `max_inbound_queue_depth` | 128 | inbound message count |
| `max_outbound_queue_depth` | 128 | outbound message count |
| `max_inbound_queue_bytes` | 8 MiB | inbound byte budget |
| `max_outbound_queue_bytes` | 8 MiB | outbound byte budget |
| `max_messages_per_window` | 1000 | rate limit messages |
| `max_bytes_per_window` | 16 MiB | rate limit bytes |
| `window_seconds` | 1.0 | rate limit window |
| `max_pending_sends` | 64 | outstanding sends |
| `max_pending_receives` | 64 | outstanding receives |
| `connect_timeout_seconds` | 10 | connect timeout |
| `receive_timeout_seconds` | 30 | receive timeout |
| `send_timeout_seconds` | 30 | send timeout |
| `idle_timeout_seconds` | 300 | idle timeout |

## Test coverage

| File | Tests |
|------|-------|
| `test_transport_interface.py` | 5 |
| `test_connection_state.py` | 7 |
| `test_queue_limits.py` | 6 |
| `test_rate_limits.py` | 5 |
| `test_memory_transport.py` | 6 |
| `test_backpressure.py` | 3 |
| `test_disconnect_rules.py` | 5 |
| **Total** | **37** |

## Threat coverage

See `docs/NETWORK_TRANSPORT_THREAT_MODEL.md`.

Covered threats:

- connection exhaustion (limits defined)
- queue flooding (bounded queues)
- slow consumer (backpressure / timeout)
- resource starvation (rate limits + byte budgets)
- timeout abuse (idle / receive / send timeouts)
- connection churn (lightweight state objects)
- bandwidth abuse (byte windows + queue caps)

## Verification gates

| Gate | Result |
|------|--------|
| `ruff check chainbreaker tests` | ✅ |
| `mypy chainbreaker tests/network` | ✅ |
| `pytest tests/network/transport/` (37) | ✅ |
| `pytest tests/network/` (123 total) | ✅ |
| `python -m build --wheel` | ✅ |
| `bandit -r chainbreaker/network` | ✅ |
| `pip-audit -r requirements.txt` | ✅ |

## Protocol V2 preservation

No changes to consensus-critical files:

- `chainbreaker/block.py`
- `chainbreaker/consensus/protocol_v2.py`
- `chainbreaker/codec.py`
- `chainbreaker/crypto.py`
- `chainbreaker/reorg.py`
- `chainbreaker/storage/backend.py`
- `vectors/`

## Explicit non-goals confirmed

Phase 8C does **not** implement:

- TCP / UDP sockets
- peer discovery
- handshake execution
- gossip
- chain sync
- block relay
- transaction propagation
- mempool networking
- peer identity / authentication
- transport encryption

These belong to later phases.

## Dependency review

The transport package imports from the network package (envelope, messages)
and from `chainbreaker.crypto`. It does not import consensus, storage,
registry, archive, or governance modules. The consensus core remains network-free.

## Conclusion

Phase 8C provides a safe, testable transport abstraction. It proves that two
endpoints can exchange validated messages under bounded memory, rate, and
timeout constraints without touching real networking or consensus.

Next milestone: **Phase 8D — Connection Manager and Handshake Execution**, only
after explicit approval.
