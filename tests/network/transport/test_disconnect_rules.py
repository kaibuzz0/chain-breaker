from __future__ import annotations

import asyncio

import pytest

from chainbreaker.network import (
    HELLO,
    NET_PROTOCOL_VERSION,
    NETWORK_ID,
    NetworkEnvelope,
    parse_envelope,
    serialize_envelope,
)
from chainbreaker.network.messages import HelloMessage
from chainbreaker.network.transport import (
    Connection,
    ConnectionState,
    TransportClosedError,
    TransportStateError,
    create_memory_transport_pair,
)


def _hello_envelope() -> NetworkEnvelope:
    payload = HelloMessage(
        protocol_version=NET_PROTOCOL_VERSION,
        network_id=NETWORK_ID,
        genesis_hash="0" * 64,
        best_height=0,
        best_chain_work="0" * 64,
        feature_bits=[],
        node_limits={},
    ).to_payload()
    return parse_envelope(serialize_envelope(HELLO, payload=payload))


def test_double_close_is_idempotent() -> None:
    return asyncio.run(_double_close_is_idempotent_coro())


async def _double_close_is_idempotent_coro() -> None:
    a, b = create_memory_transport_pair()
    await a.close()
    await a.close()
    assert not a.is_open


def test_send_after_close_raises() -> None:
    return asyncio.run(_send_after_close_raises_coro())


async def _send_after_close_raises_coro() -> None:
    a, b = create_memory_transport_pair()
    await a.close()
    with pytest.raises(TransportClosedError):
        await a.send(_hello_envelope())


def test_receive_after_close_raises() -> None:
    return asyncio.run(_receive_after_close_raises_coro())


async def _receive_after_close_raises_coro() -> None:
    a, b = create_memory_transport_pair()
    await a.close()
    with pytest.raises(TransportClosedError):
        await a.receive()


def test_connection_invalid_transition_raises() -> None:
    c = Connection("x")
    with pytest.raises(TransportStateError):
        c.ensure_open()


def test_connection_closed_state() -> None:
    c = Connection("x")
    c.transition_to(ConnectionState.OPENING)
    c.transition_to(ConnectionState.ACTIVE)
    c.transition_to(ConnectionState.CLOSED)
    assert c.state == ConnectionState.CLOSED
