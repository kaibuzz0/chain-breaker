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


def test_slow_consumer_causes_backpressure() -> None:
    return asyncio.run(_slow_consumer_causes_backpressure_coro())


async def _slow_consumer_causes_backpressure_coro() -> None:
    limits = TransportLimits(
        max_inbound_queue_depth=2,
        max_outbound_queue_depth=2,
        send_timeout_seconds=0.1,
    )
    a, b = create_memory_transport_pair(limits=limits)
    env = _hello_envelope()

    await a.send(env)
    await a.send(env)

    with pytest.raises(TransportLimitError, match="timed out"):
        await a.send(env)


def test_backpressure_relieved_by_consuming() -> None:
    return asyncio.run(_backpressure_relieved_by_consuming_coro())


async def _backpressure_relieved_by_consuming_coro() -> None:
    limits = TransportLimits(
        max_inbound_queue_depth=2,
        max_outbound_queue_depth=2,
        send_timeout_seconds=1.0,
    )
    a, b = create_memory_transport_pair(limits=limits)
    env = _hello_envelope()
    await a.send(env)
    await a.send(env)

    async def consume_one() -> None:
        await b.receive()

    task = asyncio.create_task(consume_one())
    await a.send(env)
    await task


def test_byte_capacity_backpressure() -> None:
    return asyncio.run(_byte_capacity_backpressure_coro())


async def _byte_capacity_backpressure_coro() -> None:
    limits = TransportLimits(
        max_outbound_queue_bytes=1,
        max_outbound_queue_depth=100,
        send_timeout_seconds=0.1,
    )
    a, b = create_memory_transport_pair(limits=limits)
    env = _hello_envelope()
    with pytest.raises((TransportLimitError,)):
        await a.send(env)
