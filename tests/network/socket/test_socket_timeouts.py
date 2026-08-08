from __future__ import annotations

import asyncio
import contextlib
import socket

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
from chainbreaker.network.socket import (
    SocketClosedError,
    SocketLimits,
    TCPClientTransport,
    TCPServerTransport,
)


def _hello_payload() -> bytes:
    return HelloMessage(
        protocol_version=NET_PROTOCOL_VERSION,
        network_id=NETWORK_ID,
        genesis_hash="0" * 64,
        best_height=0,
        best_chain_work="0" * 64,
        feature_bits=[],
        node_limits={},
    ).to_payload()


def _hello_envelope() -> NetworkEnvelope:
    return parse_envelope(serialize_envelope(HELLO, payload=_hello_payload()))


async def _socket_pair() -> tuple[socket.socket, socket.socket, tuple[str, int]]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    async def accept() -> tuple[socket.socket, tuple[str, int]]:
        conn, addr = server.accept()
        return conn, addr

    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_sock.setblocking(False)
    with contextlib.suppress(BlockingIOError):
        client_sock.connect((host, port))
    server_conn, addr = await accept()
    return client_sock, server_conn, addr


async def _slow_reader_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    addr = writer.get_extra_info("peername") or ("unknown", 0)
    server = TCPServerTransport(reader, writer, addr, connection_id="server")
    try:
        await asyncio.sleep(10.0)
    finally:
        await server.close()


def test_client_read_timeout() -> None:
    return asyncio.run(_client_read_timeout_coro())


async def _client_read_timeout_coro() -> None:
    limits = SocketLimits(read_timeout_seconds=0.05, write_timeout_seconds=0.05)
    server = await asyncio.start_server(_slow_reader_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    client = TCPClientTransport("127.0.0.1", port, limits=limits)
    await client.open()
    env = _hello_envelope()
    await client.send(env)
    with pytest.raises(SocketClosedError, match="timed out"):
        await client.receive()
    await client.close()
    server.close()
    await server.wait_closed()
