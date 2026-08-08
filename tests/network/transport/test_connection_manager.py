from __future__ import annotations

import asyncio

import pytest

from chainbreaker.network import (
    HELLO,
    HELLO_ACK,
    NET_PROTOCOL_VERSION,
    NETWORK_ID,
    NetworkEnvelope,
    parse_envelope,
    serialize_envelope,
)
from chainbreaker.network.messages import HelloMessage
from chainbreaker.network.transport import (
    ConnectionManager,
    HandshakeContext,
    ManagedConnection,
    PeerCapabilities,
    TransportLimitError,
    TransportLimits,
    TransportValidationError,
    create_memory_transport_pair,
)

LOCAL_FEATURES = frozenset({"headers", "blocks", "archive"})


def _context(genesis_hash: str = "0" * 64) -> HandshakeContext:
    return HandshakeContext(
        network_id=NETWORK_ID,
        genesis_hash=genesis_hash,
        local_features=LOCAL_FEATURES,
    )


def _hello_payload(
    genesis_hash: str = "0" * 64,
    network_id: str = NETWORK_ID,
    features: list[str] | None = None,
    protocol_version: int = NET_PROTOCOL_VERSION,
) -> bytes:
    return HelloMessage(
        protocol_version=protocol_version,
        network_id=network_id,
        genesis_hash=genesis_hash,
        best_height=0,
        best_chain_work="0" * 64,
        feature_bits=sorted(features or []),
        node_limits={},
    ).to_payload()


def _ack_payload(ok: bool = True, reason: str = "") -> bytes:
    import json
    return json.dumps(
        {"ok": ok, "reason": reason},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hello_envelope(
    genesis_hash: str = "0" * 64,
    network_id: str = NETWORK_ID,
    features: list[str] | None = None,
    protocol_version: int = NET_PROTOCOL_VERSION,
) -> NetworkEnvelope:
    return parse_envelope(serialize_envelope(HELLO, payload=_hello_payload(
        genesis_hash=genesis_hash, network_id=network_id, features=features, protocol_version=protocol_version
    )))


async def _run_outbound_handshake(manager: ConnectionManager, peer_key: str = "peer") -> ManagedConnection:
    """Drive the manager's outbound handshake against a simulated peer."""
    a, b = create_memory_transport_pair()
    task = asyncio.create_task(manager.accept("out", a, peer_key))

    # Peer side: receive HELLO, respond with HELLO, then receive HELLO_ACK and respond.
    hello = await b.receive()
    assert hello.message_type == HELLO
    await b.send(_hello_envelope())
    ack = await b.receive()
    assert ack.message_type == HELLO_ACK
    await b.send(parse_envelope(serialize_envelope(HELLO_ACK, payload=_ack_payload())))

    return await task


async def _run_inbound_handshake(manager: ConnectionManager, peer_key: str = "peer") -> ManagedConnection:
    """Drive the manager's inbound handshake against a simulated peer."""
    a, b = create_memory_transport_pair()
    task = asyncio.create_task(manager.register_inbound("in", a, peer_key))

    # Peer side: send HELLO, receive HELLO_ACK.
    await b.send(_hello_envelope())
    ack = await b.receive()
    assert ack.message_type == HELLO_ACK

    return await task


def test_outbound_handshake_success() -> None:
    return asyncio.run(_outbound_handshake_success_coro())


async def _outbound_handshake_success_coro() -> None:
    manager = ConnectionManager(_context(), max_connections=10)
    managed = await _run_outbound_handshake(manager)
    assert managed.is_established
    assert manager.connection_count == 1
    assert managed.capabilities == PeerCapabilities(features=frozenset())


def test_inbound_handshake_success() -> None:
    return asyncio.run(_inbound_handshake_success_coro())


async def _inbound_handshake_success_coro() -> None:
    manager = ConnectionManager(_context(), max_connections=10)
    managed = await _run_inbound_handshake(manager)
    assert managed.is_established
    assert manager.connection_count == 1


def test_reject_wrong_network() -> None:
    return asyncio.run(_reject_wrong_network_coro())


async def _reject_wrong_network_coro() -> None:
    manager = ConnectionManager(_context(), max_connections=10)
    a, b = create_memory_transport_pair()
    task = asyncio.create_task(manager.register_inbound("in", a, "bad-peer"))

    await b.send(_hello_envelope(network_id="wrong-net"))
    ack = await b.receive()
    assert ack.message_type == HELLO_ACK

    with pytest.raises(TransportValidationError):
        await task


def test_reject_wrong_genesis() -> None:
    return asyncio.run(_reject_wrong_genesis_coro())


async def _reject_wrong_genesis_coro() -> None:
    manager = ConnectionManager(_context(), max_connections=10)
    a, b = create_memory_transport_pair()
    task = asyncio.create_task(manager.register_inbound("in", a, "bad-genesis"))

    await b.send(_hello_envelope(genesis_hash="f" * 64))
    ack = await b.receive()
    assert ack.message_type == HELLO_ACK

    with pytest.raises(TransportValidationError):
        await task


def test_reject_unsupported_version() -> None:
    return asyncio.run(_reject_unsupported_version_coro())


async def _reject_unsupported_version_coro() -> None:
    manager = ConnectionManager(_context(), max_connections=10)
    a, b = create_memory_transport_pair()
    task = asyncio.create_task(manager.register_inbound("in", a, "bad-version"))

    await b.send(_hello_envelope(protocol_version=99))
    ack = await b.receive()
    assert ack.message_type == HELLO_ACK

    with pytest.raises(TransportValidationError):
        await task


def test_repeated_failed_handshake_bans_peer() -> None:
    return asyncio.run(_repeated_failed_handshake_bans_peer_coro())


async def _repeated_failed_handshake_bans_peer_coro() -> None:
    manager = ConnectionManager(_context(), max_connections=10)
    peer_key = "bad-peer"

    for i in range(3):
        a, b = create_memory_transport_pair()
        task = asyncio.create_task(manager.register_inbound(f"in-{i}", a, peer_key))
        await b.send(_hello_envelope(network_id="wrong-net"))
        await b.receive()
        with pytest.raises(TransportValidationError):
            await task

    assert manager.is_banned(peer_key)

    # New attempts from the banned peer are rejected before any handshake traffic.
    a, b = create_memory_transport_pair()
    with pytest.raises(TransportLimitError, match="banned"):
        await manager.register_inbound("in-banned", a, peer_key)


def test_handshake_timeout() -> None:
    return asyncio.run(_handshake_timeout_coro())


async def _handshake_timeout_coro() -> None:
    limits = TransportLimits(connect_timeout_seconds=0.05, receive_timeout_seconds=0.05)
    manager = ConnectionManager(_context(), max_connections=10, limits=limits)
    a, b = create_memory_transport_pair(limits=limits)

    # Peer never responds.
    task = asyncio.create_task(manager.accept("out", a, "silent-peer"))
    with pytest.raises(TransportLimitError, match="timed out"):
        await task

    assert manager.connection_count == 0


def test_connection_manager_capacity() -> None:
    return asyncio.run(_connection_manager_capacity_coro())


async def _connection_manager_capacity_coro() -> None:
    manager = ConnectionManager(_context(), max_connections=1)
    await _run_inbound_handshake(manager)
    assert manager.available_slots == 0

    a, b = create_memory_transport_pair()
    with pytest.raises(TransportLimitError, match="at capacity"):
        await manager.register_inbound("overflow", a, "other")

    await manager.remove("in")
    assert manager.connection_count == 0


def test_status_snapshot() -> None:
    return asyncio.run(_status_snapshot_coro())


async def _status_snapshot_coro() -> None:
    manager = ConnectionManager(_context(), max_connections=10)
    await _run_inbound_handshake(manager)
    status = manager.status()
    assert status["active"] == 1
    assert status["available_slots"] == 9
    assert "in" in status["connection_ids"]
