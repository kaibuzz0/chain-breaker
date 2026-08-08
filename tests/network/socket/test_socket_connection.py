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
    SocketConnection,
    SocketConnectionState,
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


def test_socket_connection_lifecycle() -> None:
    return asyncio.run(_socket_connection_lifecycle_coro())


async def _socket_connection_lifecycle_coro() -> None:
    client_sock, server_conn, _ = await _socket_pair()
    conn = SocketConnection(server_conn, "test")
    assert conn.state == SocketConnectionState.CONNECTED
    await conn.close()
    assert conn.state.name == "CLOSED"
    client_sock.close()


def test_socket_connection_send_recv() -> None:
    return asyncio.run(_socket_connection_send_recv_coro())


async def _socket_connection_send_recv_coro() -> None:
    client_sock, server_conn, _ = await _socket_pair()
    client = SocketConnection(client_sock, "client")
    server = SocketConnection(server_conn, "server")

    data = b"hello world"
    await client.send_all(data)
    received = await server.recv_exactly(len(data))
    assert received == data

    await client.close()
    await server.close()


def test_socket_connection_partial_recv() -> None:
    return asyncio.run(_socket_connection_partial_recv_coro())


async def _socket_connection_partial_recv_coro() -> None:
    client_sock, server_conn, _ = await _socket_pair()
    client = SocketConnection(client_sock, "client")
    server = SocketConnection(server_conn, "server")

    data = b"AB" * 1000
    await client.send_all(data)
    chunk = await server.recv_some()
    assert len(chunk) > 0
    assert data.startswith(chunk)

    await client.close()
    await server.close()


def test_socket_connection_close_rejects_io() -> None:
    return asyncio.run(_socket_connection_close_rejects_io_coro())


async def _socket_connection_close_rejects_io_coro() -> None:
    client_sock, server_conn, _ = await _socket_pair()
    conn = SocketConnection(server_conn, "test")
    await conn.close()
    with pytest.raises(SocketClosedError):
        await conn.send_all(b"x")
    client_sock.close()
