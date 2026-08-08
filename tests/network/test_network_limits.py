"""Tests that all network limits are enforced."""

from __future__ import annotations

import pytest

from chainbreaker.network import (
    MAX_BLOCKS_RESPONSE,
    MAX_HEADERS_RESPONSE,
    MAX_INVENTORY_ENTRIES,
    MAX_LOCATOR_SIZE,
    MAX_MESSAGE_SIZE,
    MAX_NETWORK_ID_LENGTH,
    MAX_PAYLOAD_BYTES,
    NetworkValidationError,
    OversizedPayloadError,
    serialize_envelope,
)
from chainbreaker.network.envelope import parse_envelope
from chainbreaker.network.messages import HelloMessage


def _payload() -> bytes:
    return HelloMessage(
        protocol_version=1,
        network_id="chainbreaker-scripture-v2",
        genesis_hash="0" * 64,
        best_height=0,
        best_chain_work="0" * 64,
        feature_bits=[],
        node_limits={},
    ).to_payload()


def test_max_payload_bytes_constant_sane() -> None:
    assert MAX_PAYLOAD_BYTES <= 2_000_000


def test_max_message_size_matches_envelope_plus_payload() -> None:
    # Minimum envelope + max payload must fit in MAX_MESSAGE_SIZE.
    assert MAX_MESSAGE_SIZE >= 67 + MAX_PAYLOAD_BYTES


def test_max_network_id_length_within_byte() -> None:
    assert 0 < MAX_NETWORK_ID_LENGTH <= 64


def test_oversized_payload_at_exact_boundary_rejected() -> None:
    payload = b"x" * (MAX_PAYLOAD_BYTES + 1)
    with pytest.raises(OversizedPayloadError):
        serialize_envelope(0x01, payload=payload)


def test_max_payload_accepted() -> None:
    payload = b"x" * MAX_PAYLOAD_BYTES
    raw = serialize_envelope(0x01, payload=payload)
    env = parse_envelope(raw)
    assert env.payload == payload


def test_message_too_large_exactly_one_over() -> None:
    raw = b"\x00" * (MAX_MESSAGE_SIZE + 1)
    with pytest.raises(NetworkValidationError, match="too large"):
        parse_envelope(raw)


def test_response_limits_are_reasonable() -> None:
    assert MAX_HEADERS_RESPONSE <= 2000
    assert MAX_BLOCKS_RESPONSE <= 64
    assert MAX_INVENTORY_ENTRIES <= 10000
    assert MAX_LOCATOR_SIZE <= 64
