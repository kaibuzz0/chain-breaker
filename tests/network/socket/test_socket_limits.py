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
    SocketConnection,
    SocketLimits,
    SocketTransportLimitError,
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


def test_socket_limits_prevent_oversized_send() -> None:
    return asyncio.run(_socket_limits_prevent_oversized_send_coro())


async def _socket_limits_prevent_oversized_send_coro() -> None:
    client_sock, server_conn, _ = await _socket_pair()
    limits = SocketLimits(max_message_size=1)
    client = SocketConnection(client_sock, "client", limits=limits)
    with pytest.raises(SocketTransportLimitError):
        await client.send_all(b"too-large")
    await client.close()
    server_conn.close()
