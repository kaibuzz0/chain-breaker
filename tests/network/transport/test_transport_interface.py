from __future__ import annotations

import asyncio

from chainbreaker.network import (
    HELLO,
    NET_PROTOCOL_VERSION,
    NETWORK_ID,
    NetworkEnvelope,
    parse_envelope,
    serialize_envelope,
)
from chainbreaker.network.messages import HelloMessage
from chainbreaker.network.transport import create_memory_transport_pair


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


def test_memory_pair_is_open() -> None:
    return asyncio.run(_memory_pair_is_open_coro())


async def _memory_pair_is_open_coro() -> None:
    a, b = create_memory_transport_pair()
    assert a.is_open
    assert b.is_open


def test_send_and_receive_across_pair() -> None:
    return asyncio.run(_send_and_receive_across_pair_coro())


async def _send_and_receive_across_pair_coro() -> None:
    a, b = create_memory_transport_pair()
    env = _hello_envelope()
    await a.send(env)
    received = await b.receive()
    assert received.message_type == env.message_type
    assert received.payload == env.payload


def test_bidirectional_send() -> None:
    return asyncio.run(_bidirectional_send_coro())


async def _bidirectional_send_coro() -> None:
    a, b = create_memory_transport_pair()
    env = _hello_envelope()
    await a.send(env)
    await b.send(env)
    assert (await a.receive()).message_type == HELLO
    assert (await b.receive()).message_type == HELLO


def test_close_disconnects_both() -> None:
    return asyncio.run(_close_disconnects_both_coro())


async def _close_disconnects_both_coro() -> None:
    a, b = create_memory_transport_pair()
    await a.close()
    assert not a.is_open
    assert not b.is_open


def test_status_snapshot() -> None:
    return asyncio.run(_status_snapshot_coro())


async def _status_snapshot_coro() -> None:
    a, b = create_memory_transport_pair()
    status = await a.status()
    assert status["connection_id"] == "a"
    assert status["state"] == "ACTIVE"
    assert status["open"] is True
