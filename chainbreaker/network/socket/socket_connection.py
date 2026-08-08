"""State machine and I/O helpers for a single TCP socket connection."""

from __future__ import annotations

import asyncio
import socket
from enum import Enum, auto
from typing import Any

from chainbreaker.network.socket.errors import (
    SocketClosedError,
    SocketTransportError,
    SocketTransportLimitError,
)
from chainbreaker.network.socket.limits import SocketLimits


class SocketConnectionState(Enum):
    """Lifecycle of a socket connection."""

    CONNECTING = auto()
    CONNECTED = auto()
    CLOSING = auto()
    CLOSED = auto()


_VALID_TRANSITIONS: dict[SocketConnectionState, set[SocketConnectionState]] = {
    SocketConnectionState.CONNECTING: {SocketConnectionState.CONNECTED, SocketConnectionState.CLOSING, SocketConnectionState.CLOSED},
    SocketConnectionState.CONNECTED: {SocketConnectionState.CLOSING, SocketConnectionState.CLOSED},
    SocketConnectionState.CLOSING: {SocketConnectionState.CLOSED},
    SocketConnectionState.CLOSED: set(),
}


class SocketConnection:
    """Wraps a real socket and tracks its lifecycle."""

    def __init__(
        self,
        sock: socket.socket,
        connection_id: str,
        limits: SocketLimits | None = None,
    ) -> None:
        self._sock = sock
        self.connection_id = connection_id
        self._limits = limits or SocketLimits()
        self._state = SocketConnectionState.CONNECTED if sock.fileno() != -1 else SocketConnectionState.CLOSED

    @property
    def state(self) -> SocketConnectionState:
        return self._state

    def transition_to(self, new_state: SocketConnectionState) -> None:
        if new_state not in _VALID_TRANSITIONS[self._state]:
            raise SocketTransportError(
                f"invalid socket transition {self._state.name} -> {new_state.name}"
            )
        self._state = new_state

    def ensure_open(self) -> None:
        if self._state == SocketConnectionState.CLOSED:
            raise SocketClosedError(f"socket {self.connection_id} is closed")
        if self._state not in {SocketConnectionState.CONNECTING, SocketConnectionState.CONNECTED}:
            raise SocketClosedError(f"socket {self.connection_id} is not open (state={self._state.name})")

    @property
    def is_open(self) -> bool:
        return self._state in {SocketConnectionState.CONNECTING, SocketConnectionState.CONNECTED}

    def set_timeouts(self) -> None:
        """Apply configured timeouts to the underlying socket."""
        if self._sock.fileno() == -1:
            return
        self._sock.settimeout(self._limits.read_timeout_seconds)

    async def recv_exactly(self, n: int) -> bytes:
        """Read exactly n bytes, respecting read timeout and buffer limits."""
        self.ensure_open()
        if n > self._limits.max_frame_buffer_bytes:
            raise SocketTransportLimitError(
                f"cannot read {n} bytes; exceeds buffer limit"
            )

        data = bytearray()
        self._sock.setblocking(False)
        try:
            while len(data) < n:
                try:
                    chunk = self._sock.recv(n - len(data))
                except BlockingIOError:
                    await asyncio.sleep(0.001)
                    continue
                except OSError as exc:
                    raise SocketClosedError(f"socket {self.connection_id} closed: {exc}") from exc

                if not chunk:
                    raise SocketClosedError(
                        f"socket {self.connection_id} disconnected while reading"
                    )
                data.extend(chunk)
        finally:
            self._sock.setblocking(True)

        return bytes(data)

    async def recv_some(self) -> bytes:
        """Read whatever bytes are currently available (non-blocking)."""
        self.ensure_open()
        self._sock.setblocking(False)
        try:
            try:
                return self._sock.recv(self._limits.recv_buffer_size)
            except BlockingIOError:
                return b""
            except OSError as exc:
                raise SocketClosedError(f"socket {self.connection_id} closed: {exc}") from exc
        finally:
            self._sock.setblocking(True)

    async def send_all(self, data: bytes) -> None:
        """Send all bytes, respecting write timeout."""
        self.ensure_open()
        if len(data) > self._limits.max_message_size:
            raise SocketTransportLimitError(
                f"send size {len(data)} exceeds max {self._limits.max_message_size}"
            )

        self._sock.setblocking(False)
        try:
            sent = 0
            deadline = asyncio.get_event_loop().time() + self._limits.write_timeout_seconds
            while sent < len(data):
                if asyncio.get_event_loop().time() > deadline:
                    raise SocketTransportLimitError(
                        f"socket {self.connection_id} write timed out"
                    )
                try:
                    n = self._sock.send(data[sent:])
                except BlockingIOError:
                    await asyncio.sleep(0.001)
                    continue
                except OSError as exc:
                    raise SocketClosedError(f"socket {self.connection_id} closed: {exc}") from exc
                sent += n
        finally:
            self._sock.setblocking(True)

    async def close(self) -> None:
        if self._state == SocketConnectionState.CLOSED:
            return
        try:
            self.transition_to(SocketConnectionState.CLOSING)
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:  # nosec B110
            pass
        finally:
            self._sock.close()
            self._state = SocketConnectionState.CLOSED

    def status(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "state": self._state.name,
            "open": self.is_open,
        }
