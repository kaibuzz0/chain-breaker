from __future__ import annotations

import contextlib
import socket

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


def test_split_frame_across_many_packets() -> None:
    framing = EnvelopeFraming()
    env = _hello_envelope()
    raw = serialize_envelope(env.message_type, env.flags, env.payload)
    for byte in (raw[i:i + 1] for i in range(len(raw))):
        result = framing.consume(byte)
        if result:
            break
    assert len(result) == 1
    assert result[0].payload == env.payload


def test_disconnect_mid_frame() -> None:
    framing = EnvelopeFraming()
    env = _hello_envelope()
    raw = serialize_envelope(env.message_type, env.flags, env.payload)
    framing.consume(raw[:10])
    assert framing.consume(b"") == []


def test_junk_bytes_dropped_until_sync() -> None:
    framing = EnvelopeFraming()
    env = _hello_envelope()
    raw = serialize_envelope(env.message_type, env.flags, env.payload)
    garbage = b"\x00\x01\x02\x03"
    result = framing.consume(garbage + raw)
    assert len(result) == 1
    assert result[0].payload == env.payload
