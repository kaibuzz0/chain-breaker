"""Tests for Protocol v2 genesis block and registry state.

This module is part of Milestone 4B.  It verifies the hard-coded v2 genesis
constants against the specification in docs/GENESIS_V2_SPECIFICATION.md.
"""

from __future__ import annotations

from chainbreaker.block import (
    GENESIS_GOVERNANCE_KEYS,
    GENESIS_HASH,
    GENESIS_HEADER_BYTES,
    GENESIS_NONCE,
    GENESIS_REGISTRY_ROOT,
    GENESIS_TARGET,
    GENESIS_THRESHOLD,
    GENESIS_TIMESTAMP,
    NETWORK_ID,
    PROTOCOL_VERSION,
    BlockHeaderV2,
    header_v2_hash,
    satisfies_pow,
    verify_genesis,
)
from chainbreaker.codec import BinaryCodec
from chainbreaker.registry_state import RegistryState, registry_root


def test_genesis_protocol_version():
    assert PROTOCOL_VERSION == 2


def test_genesis_network_id():
    assert NETWORK_ID == "chainbreaker-scripture-v2"


def test_genesis_governance_keys_sorted_and_count():
    assert sorted(GENESIS_GOVERNANCE_KEYS) == GENESIS_GOVERNANCE_KEYS
    assert len(GENESIS_GOVERNANCE_KEYS) == 3
    assert GENESIS_THRESHOLD == 2


def test_genesis_registry_state_matches_constants():
    state = RegistryState.genesis(
        governance_keys=list(GENESIS_GOVERNANCE_KEYS),
        threshold=GENESIS_THRESHOLD,
    )
    assert registry_root(state) == GENESIS_REGISTRY_ROOT


def test_genesis_header_bytes_exact_length():
    assert len(GENESIS_HEADER_BYTES) == 149


def test_genesis_header_decode_matches_constants():
    header, offset = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)
    assert offset == 149
    assert header["version"] == 2
    assert header["prev_hash"] == "0" * 64
    assert header["merkle_root"] == "0" * 64
    assert header["registry_root"] == GENESIS_REGISTRY_ROOT
    assert header["timestamp"] == GENESIS_TIMESTAMP
    assert header["nonce"] == GENESIS_NONCE


def test_genesis_hash_matches_double_sha256():
    header, _ = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)
    assert header_v2_hash(header) == GENESIS_HASH


def test_genesis_hash_satisfies_target():
    assert satisfies_pow(GENESIS_HASH, GENESIS_TARGET)


def test_verify_genesis_default_passes():
    assert verify_genesis() is True


def test_verify_genesis_with_provided_bytes_passes():
    assert verify_genesis(GENESIS_HEADER_BYTES, GENESIS_HASH, GENESIS_REGISTRY_ROOT)


def test_verify_genesis_rejects_wrong_bytes():
    bad = bytearray(GENESIS_HEADER_BYTES)
    bad[-1] ^= 0x01
    assert verify_genesis(bytes(bad)) is False


def test_verify_genesis_rejects_truncated():
    assert verify_genesis(GENESIS_HEADER_BYTES[:-1]) is False


def test_block_header_v2_genesis_round_trip():
    header, _ = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)
    bh = BlockHeaderV2.from_dict(header)
    assert BinaryCodec.encode_header_v2(bh.to_dict()) == GENESIS_HEADER_BYTES
    assert bh.hash() == GENESIS_HASH
