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
    TransportClosedError,
    TransportLimitError,
    TransportLimits,
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


def test_memory_transport_round_trip() -> None:
    return asyncio.run(_memory_transport_round_trip_coro())


async def _memory_transport_round_trip_coro() -> None:
    a, b = create_memory_transport_pair()
    env = _hello_envelope()
    await a.send(env)
    received = await b.receive()
    assert received.payload == env.payload


def test_memory_transport_close_prevents_send() -> None:
    return asyncio.run(_memory_transport_close_prevents_send_coro())


async def _memory_transport_close_prevents_send_coro() -> None:
    a, b = create_memory_transport_pair()
    await a.close()
    with pytest.raises(TransportClosedError):
        await a.send(_hello_envelope())


def test_memory_transport_rate_limit() -> None:
    return asyncio.run(_memory_transport_rate_limit_coro())


async def _memory_transport_rate_limit_coro() -> None:
    limits = TransportLimits(
        max_messages_per_window=1,
        max_bytes_per_window=1_000_000,
        window_seconds=1.0,
    )
    a, b = create_memory_transport_pair(limits=limits)
    env = _hello_envelope()
    await a.send(env)
    with pytest.raises(TransportLimitError, match="rate limit"):
        await a.send(env)


def test_memory_transport_receive_timeout() -> None:
    return asyncio.run(_memory_transport_receive_timeout_coro())


async def _memory_transport_receive_timeout_coro() -> None:
    limits = TransportLimits(receive_timeout_seconds=0.05)
    a, b = create_memory_transport_pair(limits=limits)
    with pytest.raises(TransportLimitError, match="timed out"):
        await b.receive()


def test_memory_transport_send_timeout_on_full_queue() -> None:
    return asyncio.run(_memory_transport_send_timeout_on_full_queue_coro())


async def _memory_transport_send_timeout_on_full_queue_coro() -> None:
    limits = TransportLimits(
        max_outbound_queue_depth=1,
        send_timeout_seconds=0.05,
    )
    a, b = create_memory_transport_pair(limits=limits)
    env = _hello_envelope()
    await a.send(env)
    with pytest.raises(TransportLimitError, match="timed out"):
        await a.send(env)


def test_memory_transport_idle_detection() -> None:
    return asyncio.run(_memory_transport_idle_detection_coro())


async def _memory_transport_idle_detection_coro() -> None:
    limits = TransportLimits(idle_timeout_seconds=0.05)
    a, b = create_memory_transport_pair(limits=limits)
    await asyncio.sleep(0.1)
    assert a.check_idle()
    assert b.check_idle()
