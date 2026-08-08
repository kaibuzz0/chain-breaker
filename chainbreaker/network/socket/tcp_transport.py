"""TCP socket implementations of the abstract Transport interface."""

from __future__ import annotations

import asyncio
from typing import Any

from chainbreaker.network import NetworkEnvelope, serialize_envelope
from chainbreaker.network.socket.errors import (
    SocketClosedError,
    SocketTransportError,
    SocketTransportLimitError,
)
from chainbreaker.network.socket.framing import EnvelopeFraming
from chainbreaker.network.socket.limits import SocketLimits


class TCPClientTransport:
    """Client-side TCP transport that connects to a remote endpoint."""

    def __init__(
        self,
        host: str,
        port: int,
        limits: SocketLimits | None = None,
        connection_id: str = "client",
    ) -> None:
        self._host = host
        self._port = port
        self._limits = limits or SocketLimits()
        self._connection_id = connection_id
        self._framing = EnvelopeFraming(limits=self._limits)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    @property
    def is_open(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def open(self) -> None:
        if self._writer is not None:
            raise SocketTransportError("transport already opened")
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._limits.connect_timeout_seconds,
            )
        except TimeoutError as exc:
            raise SocketTransportError("connect timed out") from exc
        except OSError as exc:
            raise SocketTransportError(f"connect failed: {exc}") from exc

    async def send(self, envelope: NetworkEnvelope) -> None:
        if not self.is_open:
            raise SocketClosedError("transport is not open")
        if self._writer is None:
            raise SocketClosedError("transport is not open")
        raw = serialize_envelope(envelope.message_type, envelope.flags, envelope.payload)
        if len(raw) > self._limits.max_message_size:
            raise SocketTransportLimitError(
                f"send size {len(raw)} exceeds max {self._limits.max_message_size}"
            )
        self._writer.write(raw)
        await asyncio.wait_for(self._writer.drain(), timeout=self._limits.write_timeout_seconds)

    async def receive(self) -> NetworkEnvelope:
        if not self.is_open:
            raise SocketClosedError("transport is not open")
        if self._reader is None:
            raise SocketClosedError("transport is not open")
        while True:
            envelopes = self._framing.consume(b"")
            if envelopes:
                return envelopes[0]
            try:
                data = await asyncio.wait_for(
                    self._reader.read(self._limits.recv_buffer_size),
                    timeout=self._limits.read_timeout_seconds,
                )
            except TimeoutError as exc:
                raise SocketClosedError("read timed out") from exc
            if not data:
                raise SocketClosedError("connection closed by peer")
            envelopes = self._framing.consume(data)
            if envelopes:
                return envelopes[0]

    async def close(self) -> None:
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # nosec B110
                pass
            self._writer = None
            self._reader = None

    async def status(self) -> dict[str, Any]:
        return {
            "connection_id": self._connection_id,
            "state": "CONNECTED" if self.is_open else "CLOSED",
            "open": self.is_open,
        }


class TCPServerTransport:
    """Server-side TCP transport wrapping an accepted client stream."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        address: tuple[str, int],
        limits: SocketLimits | None = None,
        connection_id: str = "server",
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._address = address
        self._limits = limits or SocketLimits()
        self._connection_id = connection_id
        self._framing = EnvelopeFraming(limits=self._limits)

    @property
    def is_open(self) -> bool:
        return not self._writer.is_closing()

    async def send(self, envelope: NetworkEnvelope) -> None:
        if not self.is_open:
            raise SocketClosedError("transport is not open")
        raw = serialize_envelope(envelope.message_type, envelope.flags, envelope.payload)
        if len(raw) > self._limits.max_message_size:
            raise SocketTransportLimitError(
                f"send size {len(raw)} exceeds max {self._limits.max_message_size}"
            )
        self._writer.write(raw)
        await asyncio.wait_for(self._writer.drain(), timeout=self._limits.write_timeout_seconds)

    async def receive(self) -> NetworkEnvelope:
        if not self.is_open:
            raise SocketClosedError("transport is not open")
        while True:
            envelopes = self._framing.consume(b"")
            if envelopes:
                return envelopes[0]
            try:
                data = await asyncio.wait_for(
                    self._reader.read(self._limits.recv_buffer_size),
                    timeout=self._limits.read_timeout_seconds,
                )
            except TimeoutError as exc:
                raise SocketClosedError("read timed out") from exc
            if not data:
                raise SocketClosedError("connection closed by peer")
            envelopes = self._framing.consume(data)
            if envelopes:
                return envelopes[0]

    async def close(self) -> None:
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:  # nosec B110
            pass

    async def status(self) -> dict[str, Any]:
        return {
            "connection_id": self._connection_id,
            "state": "CONNECTED" if self.is_open else "CLOSED",
            "open": self.is_open,
            "address": self._address,
        }
