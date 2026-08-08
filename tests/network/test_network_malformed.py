"""Tests for malformed and adversarial network inputs."""

from __future__ import annotations

import struct

import pytest

from chainbreaker.crypto import HashEngine
from chainbreaker.network import (
    CBN1_MAGIC,
    HELLO,
    MAX_MESSAGE_SIZE,
    MAX_PAYLOAD_BYTES,
    NetworkValidationError,
    PayloadHashMismatchError,
    UnknownMessageTypeError,
    parse_envelope,
)


def make_minimal_hello(payload: bytes = b"") -> bytes:
    """Build a syntactically valid hello envelope with arbitrary payload."""
    network_id = b"chainbreaker-scripture-v2"
    payload_hash = HashEngine.sha256(payload)
    return (
        CBN1_MAGIC
        + struct.pack(">H", 1)
        + struct.pack(">B", len(network_id))
        + network_id
        + struct.pack(">B", HELLO)
        + struct.pack(">B", 0)
        + struct.pack(">I", len(payload))
        + payload_hash
        + payload
    )


def test_all_zeros() -> None:
    with pytest.raises(NetworkValidationError):
        parse_envelope(bytes(MAX_MESSAGE_SIZE))


def test_random_bytes() -> None:
    import random
    data = bytes(random.randint(0, 255) for _ in range(4096))
    with pytest.raises(NetworkValidationError):
        parse_envelope(data)


def test_magic_only() -> None:
    with pytest.raises(NetworkValidationError, match="too short"):
        parse_envelope(CBN1_MAGIC)


def test_zero_payload_length_valid_hash() -> None:
    raw = make_minimal_hello(b"")
    env = parse_envelope(raw)
    assert env.payload == b""


def test_truncated_header_at_each_offset() -> None:
    raw = make_minimal_hello(b"payload")
    for cut in range(1, len(raw)):
        with pytest.raises(NetworkValidationError):
            parse_envelope(raw[:cut])


def test_flipped_bits_in_payload_hash() -> None:
    raw = bytearray(make_minimal_hello(b"payload"))
    # Payload hash sits just before payload.
    payload_offset = len(raw) - len(b"payload")
    hash_offset = payload_offset - 32
    raw[hash_offset] ^= 0xFF
    with pytest.raises(PayloadHashMismatchError):
        parse_envelope(bytes(raw))


def test_wrong_length_smaller_than_payload() -> None:
    raw = bytearray(make_minimal_hello(b"payload"))
    # Claim length 2, but payload is 7 bytes.
    # Need to adjust the length field at offset 4+2+1+22+1+1 = 31
    offset = 4 + 2 + 1 + len("chainbreaker-scripture-v2") + 1 + 1
    raw[offset : offset + 4] = struct.pack(">I", 2)
    with pytest.raises(NetworkValidationError, match="size mismatch"):
        parse_envelope(bytes(raw))


def test_length_larger_than_remaining_data() -> None:
    raw = bytearray(make_minimal_hello(b"payload"))
    offset = 4 + 2 + 1 + len("chainbreaker-scripture-v2") + 1 + 1
    raw[offset : offset + 4] = struct.pack(">I", MAX_PAYLOAD_BYTES)
    with pytest.raises(NetworkValidationError, match="size mismatch"):
        parse_envelope(bytes(raw))


def test_message_type_zero() -> None:
    raw = bytearray(make_minimal_hello(b"payload"))
    offset = 4 + 2 + 1 + len("chainbreaker-scripture-v2")
    raw[offset] = 0x00
    with pytest.raises(UnknownMessageTypeError):
        parse_envelope(bytes(raw))


def test_message_type_reserved() -> None:
    raw = bytearray(make_minimal_hello(b"payload"))
    offset = 4 + 2 + 1 + len("chainbreaker-scripture-v2")
    raw[offset] = 0x0E
    with pytest.raises(UnknownMessageTypeError):
        parse_envelope(bytes(raw))


def test_negative_payload_length_encoded_as_large_u32() -> None:
    # A 32-bit unsigned value representing a huge length should be rejected by
    # the oversized-payload check before allocation.
    raw = bytearray(make_minimal_hello(b""))
    offset = 4 + 2 + 1 + len("chainbreaker-scripture-v2") + 1 + 1
    raw[offset : offset + 4] = struct.pack(">I", 0xFFFFFFFF)
    with pytest.raises(NetworkValidationError, match="exceeds"):
        parse_envelope(bytes(raw))


def test_payload_with_embedded_nulls() -> None:
    payload = b"\x00" * 100
    raw = make_minimal_hello(payload)
    env = parse_envelope(raw)
    assert env.payload == payload
