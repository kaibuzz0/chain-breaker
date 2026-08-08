from __future__ import annotations

import asyncio

import pytest

from chainbreaker.network.transport import (
    BoundedMessageQueue,
    TransportClosedError,
    TransportLimitError,
)


def test_queue_put_get() -> None:
    return asyncio.run(_queue_put_get_coro())


async def _queue_put_get_coro() -> None:
    q = BoundedMessageQueue(10, 1024)
    await q.put(b"hello")
    assert await q.get() == b"hello"


def test_queue_depth_limit() -> None:
    return asyncio.run(_queue_depth_limit_coro())


async def _queue_depth_limit_coro() -> None:
    q = BoundedMessageQueue(2, 1024)
    await q.put(b"a")
    await q.put(b"b")
    with pytest.raises(TransportLimitError):
        await q.put(b"c", timeout=0.05)


def test_queue_byte_limit() -> None:
    return asyncio.run(_queue_byte_limit_coro())


async def _queue_byte_limit_coro() -> None:
    q = BoundedMessageQueue(10, 10)
    with pytest.raises(TransportLimitError):
        await q.put(b"too-large-for-byte-capacity")


def test_queue_put_after_close() -> None:
    return asyncio.run(_queue_put_after_close_coro())


async def _queue_put_after_close_coro() -> None:
    q = BoundedMessageQueue(10, 1024)
    q.close()
    with pytest.raises(TransportClosedError):
        await q.put(b"x")


def test_queue_get_after_close_empty() -> None:
    return asyncio.run(_queue_get_after_close_empty_coro())


async def _queue_get_after_close_empty_coro() -> None:
    q = BoundedMessageQueue(10, 1024)
    q.close()
    with pytest.raises(TransportClosedError):
        await q.get(timeout=0.05)


def test_queue_backpressure_relieved_by_consumer() -> None:
    return asyncio.run(_queue_backpressure_relieved_by_consumer_coro())


async def _queue_backpressure_relieved_by_consumer_coro() -> None:
    q = BoundedMessageQueue(2, 1024)
    await q.put(b"a")
    await q.put(b"b")

    async def consume() -> None:
        await q.get()

    task = asyncio.create_task(consume())
    await q.put(b"c", timeout=1.0)
    await task
