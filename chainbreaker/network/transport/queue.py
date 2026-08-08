"""Bounded message queues for transport endpoints."""

from __future__ import annotations

from asyncio import Queue, wait_for
from asyncio import TimeoutError as AsyncTimeoutError
from dataclasses import dataclass

from .errors import TransportClosedError, TransportLimitError


@dataclass(frozen=True, slots=True)
class QueueMetrics:
    depth: int
    bytes_used: int
    capacity: int
    bytes_capacity: int
    drops: int


class BoundedMessageQueue:
    """A queue with bounded message count and byte capacity.

    Enforces backpressure: puts block when full (with timeout), preventing
    unbounded memory growth.
    """

    def __init__(self, max_depth: int, max_bytes: int, name: str = "queue") -> None:
        if max_depth <= 0:
            raise ValueError("max_depth must be positive")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._max_depth = max_depth
        self._max_bytes = max_bytes
        self._name = name
        self._queue: Queue[bytes] = Queue(maxsize=max_depth)
        self._bytes_used = 0
        self._drops = 0
        self._closed = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def put(self, item: bytes, timeout: float | None = None) -> None:
        """Put a message, awaiting space if needed.

        Raises TransportLimitError on timeout or if the queue is closed.
        """
        if self._closed:
            raise TransportClosedError(f"{self._name} is closed")

        item_size = len(item)
        if item_size > self._max_bytes:
            self._drops += 1
            raise TransportLimitError(
                f"message size {item_size} exceeds queue byte capacity {self._max_bytes}"
            )

        # Wait until there is enough byte budget
        while self._bytes_used + item_size > self._max_bytes:
            if timeout is not None and timeout <= 0:
                self._drops += 1
                raise TransportLimitError(f"{self._name} byte budget exhausted")
            # Briefly wait for consumer; this is cooperative backpressure
            try:
                await wait_for(self._queue.get(), timeout=0.05 if timeout is None else min(0.05, timeout))
                self._bytes_used -= len(self._queue.get_nowait())
            except AsyncTimeoutError:
                pass
            if self._closed:
                raise TransportClosedError(f"{self._name} is closed")

        try:
            if timeout is None:
                await self._queue.put(item)
            else:
                await wait_for(self._queue.put(item), timeout=timeout)
        except AsyncTimeoutError:
            self._drops += 1
            raise TransportLimitError(f"{self._name} put timed out") from None

        self._bytes_used += item_size

    async def get(self, timeout: float | None = None) -> bytes:
        """Get a message from the queue.

        Raises TransportClosedError when closed and empty.
        """
        if self._closed and self._queue.empty():
            raise TransportClosedError(f"{self._name} is closed")

        try:
            if timeout is None:
                item = await self._queue.get()
            else:
                item = await wait_for(self._queue.get(), timeout=timeout)
        except AsyncTimeoutError as exc:
            raise TransportLimitError(f"{self._name} get timed out") from exc

        self._bytes_used -= len(item)
        return item

    def close(self) -> None:
        self._closed = True

    def metrics(self) -> QueueMetrics:
        return QueueMetrics(
            depth=self._queue.qsize(),
            bytes_used=max(0, self._bytes_used),
            capacity=self._max_depth,
            bytes_capacity=self._max_bytes,
            drops=self._drops,
        )
