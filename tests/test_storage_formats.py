"""Tests for chainbreaker.storage formats."""

from __future__ import annotations

import pytest

from chainbreaker.block import GENESIS_HASH, NETWORK_ID, BlockHeaderV2, BlockV2
from chainbreaker.storage.formats import (
    BLOCK_MAGIC,
    BLOCK_TRAILING,
    decode_block_record,
    decode_head,
    decode_journal_record,
    encode_block_record,
    encode_head,
    encode_journal_record,
)


def test_block_record_roundtrip():
    header = BlockHeaderV2(
        version=2,
        prev_hash="0" * 64,
        merkle_root="0" * 64,
        registry_root="1" * 64,
        timestamp=1704067201,
        target=2 ** 200,
        nonce=0,
    )
    block = BlockV2(header=header, transactions=[{"foo": "bar"}])
    data = encode_block_record(block)
    assert data.startswith(BLOCK_MAGIC)
    assert data.endswith(BLOCK_TRAILING)
    decoded = decode_block_record(data)
    assert decoded.header.hash() == block.header.hash()
    assert decoded.transactions == block.transactions


def test_block_record_rejects_trailing_bytes():
    header = BlockHeaderV2(
        version=2,
        prev_hash="0" * 64,
        merkle_root="0" * 64,
        registry_root="1" * 64,
        timestamp=1704067201,
        target=2 ** 200,
        nonce=0,
    )
    block = BlockV2(header=header, transactions=[])
    data = encode_block_record(block) + b"extra"
    with pytest.raises(ValueError, match="block record size mismatch"):
        decode_block_record(data)


def test_head_roundtrip():
    data = encode_head(7, "a" * 64, NETWORK_ID, GENESIS_HASH)
    decoded = decode_head(data)
    assert decoded["height"] == 7
    assert decoded["block_hash"] == "a" * 64
    assert decoded["network_id"] == NETWORK_ID
    assert decoded["genesis_hash"] == GENESIS_HASH
    assert decoded["format_version"] == 1


def test_journal_record_roundtrip():
    payload = b"hello"
    record = encode_journal_record(0x01, 1, 2, payload)
    decoded, offset = decode_journal_record(record)
    assert decoded["type"] == 0x01
    assert decoded["seq"] == 1
    assert decoded["height"] == 2
    assert decoded["payload"] == payload
    assert offset == len(record)


def test_journal_record_checksum_detects_corruption():
    record = encode_journal_record(0x01, 1, 2, b"hello")
    bad = record[:-1] + b"x"
    with pytest.raises(ValueError, match="checksum mismatch"):
        decode_journal_record(bad)
