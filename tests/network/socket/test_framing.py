from __future__ import annotations

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
    EnvelopeFraming,
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


def test_framing_single_envelope() -> None:
    framing = EnvelopeFraming()
    env = _hello_envelope()
    raw = serialize_envelope(env.message_type, env.flags, env.payload)
    result = framing.consume(raw)
    assert len(result) == 1
    assert result[0].message_type == HELLO
    assert result[0].payload == env.payload


def test_framing_split_header_and_payload() -> None:
    framing = EnvelopeFraming()
    env = _hello_envelope()
    raw = serialize_envelope(env.message_type, env.flags, env.payload)
    mid = len(raw) // 2
    assert framing.consume(raw[:mid]) == []
    result = framing.consume(raw[mid:])
    assert len(result) == 1


def test_framing_multiple_envelopes() -> None:
    framing = EnvelopeFraming()
    env = _hello_envelope()
    raw = serialize_envelope(env.message_type, env.flags, env.payload)
    result = framing.consume(raw + raw)
    assert len(result) == 2


def test_framing_oversized_declared_payload() -> None:
    framing = EnvelopeFraming(SocketLimits(max_message_size=1))
    env = _hello_envelope()
    raw = serialize_envelope(env.message_type, env.flags, env.payload)
    with pytest.raises(SocketTransportLimitError):
        framing.consume(raw)


def test_framing_buffer_limit() -> None:
    framing = EnvelopeFraming(SocketLimits(max_frame_buffer_bytes=1))
    env = _hello_envelope()
    raw = serialize_envelope(env.message_type, env.flags, env.payload)
    with pytest.raises(SocketTransportLimitError):
        framing.consume(raw)
