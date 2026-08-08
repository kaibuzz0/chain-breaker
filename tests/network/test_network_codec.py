"""Tests for the network envelope parser and serializer."""

from __future__ import annotations

import pytest

from chainbreaker.crypto import HashEngine
from chainbreaker.network import (
    CBN1_MAGIC,
    HELLO,
    MAX_MESSAGE_SIZE,
    MAX_NETWORK_ID_LENGTH,
    MAX_PAYLOAD_BYTES,
    NET_PROTOCOL_VERSION,
    NETWORK_ID,
    NetworkValidationError,
    OversizedPayloadError,
    PayloadHashMismatchError,
    UnknownMessageTypeError,
    parse_envelope,
    serialize_envelope,
)
from chainbreaker.network.messages import HelloMessage


def _hello_payload() -> bytes:
    msg = HelloMessage(
        protocol_version=NET_PROTOCOL_VERSION,
        network_id=NETWORK_ID,
        genesis_hash="0" * 64,
        best_height=0,
        best_chain_work="0" * 64,
        feature_bits=[],
        node_limits={},
    )
    return msg.to_payload()


def test_serialize_then_parse_round_trip() -> None:
    payload = _hello_payload()
    raw = serialize_envelope(HELLO, payload=payload)
    env = parse_envelope(raw)
    assert env.message_type == HELLO
    assert env.flags == 0
    assert env.payload == payload
    decoded = HelloMessage.from_payload(env.payload)
    assert decoded.genesis_hash == "0" * 64


def test_empty_message_rejected() -> None:
    with pytest.raises(NetworkValidationError, match="too short"):
        parse_envelope(b"")


def test_truncated_envelope_rejected() -> None:
    raw = serialize_envelope(HELLO, payload=_hello_payload())
    with pytest.raises(NetworkValidationError, match="too short"):
        parse_envelope(raw[:20])


def test_truncated_payload_rejected() -> None:
    raw = serialize_envelope(HELLO, payload=_hello_payload())
    with pytest.raises(NetworkValidationError, match="size mismatch"):
        parse_envelope(raw[:-1])


def test_wrong_magic_rejected() -> None:
    raw = serialize_envelope(HELLO, payload=_hello_payload())
    bad = b"XXXX" + raw[4:]
    with pytest.raises(NetworkValidationError, match="bad magic"):
        parse_envelope(bad)


def test_wrong_protocol_version_rejected() -> None:
    raw = bytearray(serialize_envelope(HELLO, payload=_hello_payload()))
    # protocol version is bytes 4-5, big-endian
    raw[4] = 0xFF
    raw[5] = 0xFF
    with pytest.raises(NetworkValidationError, match="unsupported protocol version"):
        parse_envelope(bytes(raw))


def test_unknown_message_type_rejected() -> None:
    raw = serialize_envelope(HELLO, payload=_hello_payload())
    # message type byte offset = 4 + 2 + 1 + len(NETWORK_ID) = 29
    network_id_len = len(NETWORK_ID.encode("utf-8"))
    offset = 4 + 2 + 1 + network_id_len
    bad = bytearray(raw)
    bad[offset] = 0xFF
    with pytest.raises(UnknownMessageTypeError):
        parse_envelope(bytes(bad))


def test_oversized_payload_rejected() -> None:
    big = b"x" * (MAX_PAYLOAD_BYTES + 1)
    with pytest.raises(OversizedPayloadError):
        serialize_envelope(HELLO, payload=big)


def test_oversized_message_length_rejected() -> None:
    # Build a message claiming a payload larger than allowed.
    import struct

    network_id_len = len(NETWORK_ID.encode("utf-8"))
    payload_hash = HashEngine.sha256(b"")
    header = (
        CBN1_MAGIC
        + struct.pack(">H", NET_PROTOCOL_VERSION)
        + struct.pack(">B", network_id_len)
        + NETWORK_ID.encode("utf-8")
        + struct.pack(">B", HELLO)
        + struct.pack(">B", 0)
        + struct.pack(">I", MAX_PAYLOAD_BYTES + 1)
        + payload_hash
    )
    raw = header + b""
    with pytest.raises(OversizedPayloadError, match="exceeds"):
        parse_envelope(raw)


def test_payload_hash_mismatch_rejected() -> None:
    raw = serialize_envelope(HELLO, payload=_hello_payload())
    # Corrupt the payload
    bad = bytearray(raw)
    bad[-1] ^= 0xFF
    with pytest.raises(PayloadHashMismatchError):
        parse_envelope(bytes(bad))


def test_extra_trailing_bytes_rejected() -> None:
    raw = serialize_envelope(HELLO, payload=_hello_payload())
    with pytest.raises(NetworkValidationError, match="size mismatch"):
        parse_envelope(raw + b"\x00")


def test_reserved_flags_rejected() -> None:
    with pytest.raises(NetworkValidationError, match="reserved flags"):
        serialize_envelope(HELLO, flags=0x04, payload=_hello_payload())


def test_invalid_network_id_length_rejected() -> None:
    import struct

    header = (
        CBN1_MAGIC
        + struct.pack(">H", NET_PROTOCOL_VERSION)
        + struct.pack(">B", MAX_NETWORK_ID_LENGTH + 1)
    )
    with pytest.raises(NetworkValidationError, match="invalid network_id length"):
        parse_envelope(header + b"\x00" * 100)


def test_wrong_network_id_rejected() -> None:
    import struct

    payload = b"x" * 100
    payload_hash = HashEngine.sha256(payload)
    header = (
        CBN1_MAGIC
        + struct.pack(">H", NET_PROTOCOL_VERSION)
        + struct.pack(">B", 5)
        + b"wrong"
        + struct.pack(">B", HELLO)
        + struct.pack(">B", 0)
        + struct.pack(">I", len(payload))
        + payload_hash
    )
    with pytest.raises(NetworkValidationError, match="wrong network_id"):
        parse_envelope(header + payload)


def test_message_too_large_rejected() -> None:
    with pytest.raises(NetworkValidationError, match="too large"):
        parse_envelope(b"\x00" * (MAX_MESSAGE_SIZE + 1))
