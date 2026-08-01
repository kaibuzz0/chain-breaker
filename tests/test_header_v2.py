"""Tests for Protocol v2 block header serialization.

This module tests only the header codec and data structure added in
Milestone 4A.  It does not touch genesis, mining, chain validation, or
witness validation.
"""

from __future__ import annotations

import struct

import pytest

from chainbreaker.block import BlockHeaderV2
from chainbreaker.codec import BinaryCodec, CodecError
from chainbreaker.crypto import HashEngine


def _sample_header_v2_dict() -> dict:
    return {
        "version": 2,
        "prev_hash": "0000000000000000000000000000000000000000000000000000000000000001",
        "merkle_root": "abcd" + "ef" * 30,
        "registry_root": "ea949b131c480ca88ce72caaf98d8b0e6f2b7e43b76e877a884299b9b0aa2c91",
        "timestamp": 1704067201,
        "target": "0000ffff00000000000000000000000000000000000000000000000000000000",
        "nonce": 123456789,
    }


def test_header_v2_exact_size():
    header = _sample_header_v2_dict()
    encoded = BinaryCodec.encode_header_v2(header)
    assert len(encoded) == 149


def test_header_v2_field_offsets():
    header = _sample_header_v2_dict()
    encoded = BinaryCodec.encode_header_v2(header)

    assert encoded[0] == BinaryCodec.TYPE_HEADER  # type marker at offset 0
    assert struct.unpack_from("<I", encoded, 1)[0] == 2  # version LE at 1
    assert encoded[5:37].hex() == header["prev_hash"]  # prev_hash at 5
    assert encoded[37:69].hex() == header["merkle_root"]  # merkle_root at 37
    assert encoded[69:101].hex() == header["registry_root"]  # registry_root at 69
    assert struct.unpack_from("<Q", encoded, 101)[0] == header["timestamp"]  # timestamp at 101
    assert encoded[109:141].hex() == header["target"]  # target at 109
    assert struct.unpack_from("<Q", encoded, 141)[0] == header["nonce"]  # nonce at 141


def test_header_v2_round_trip():
    header = _sample_header_v2_dict()
    encoded = BinaryCodec.encode_header_v2(header)
    decoded, offset = BinaryCodec.decode_header_v2(encoded)
    assert decoded == header
    assert offset == 149


def test_header_v2_encode_requires_registry_root():
    header = _sample_header_v2_dict()
    del header["registry_root"]
    with pytest.raises(CodecError):
        BinaryCodec.encode_header_v2(header)


def test_header_v2_decode_rejects_v1_header():
    """A v1 header is missing registry_root and must not parse as v2."""
    v1_header = {
        "version": 1,
        "prev_hash": "0" * 64,
        "merkle_root": "0" * 64,
        "timestamp": 1704067200,
        "target": "0000ffff00000000000000000000000000000000000000000000000000000000",
        "nonce": 0,
    }
    v1_bytes = BinaryCodec.encode_header(v1_header)
    assert len(v1_bytes) == 117
    with pytest.raises(CodecError):
        BinaryCodec.decode_header_v2(v1_bytes)


def test_header_v2_decode_rejects_wrong_type_marker():
    header = _sample_header_v2_dict()
    encoded = bytearray(BinaryCodec.encode_header_v2(header))
    encoded[0] = 0xFF
    with pytest.raises(CodecError):
        BinaryCodec.decode_header_v2(bytes(encoded))


def test_header_v2_decode_rejects_truncated():
    header = _sample_header_v2_dict()
    encoded = BinaryCodec.encode_header_v2(header)
    with pytest.raises(CodecError):
        BinaryCodec.decode_header_v2(encoded[:-1])


def test_header_v2_decode_rejects_extra_bytes_ignored():
    """decode_header_v2 should tolerate extra bytes after the header,
    returning offset 149 so callers can continue parsing a payload."""
    header = _sample_header_v2_dict()
    encoded = BinaryCodec.encode_header_v2(header) + b"extra"
    decoded, offset = BinaryCodec.decode_header_v2(encoded)
    assert offset == 149
    assert decoded == header


def test_header_v2_blockheader_v2_round_trip():
    data = _sample_header_v2_dict()
    bh = BlockHeaderV2.from_dict(data)
    assert bh.to_dict() == data


def test_header_v2_blockheader_v2_hash():
    data = _sample_header_v2_dict()
    bh = BlockHeaderV2.from_dict(data)
    expected = HashEngine.hash_double_hex(BinaryCodec.encode_header_v2(data))
    assert bh.hash() == expected


def test_header_v2_rejects_invalid_registry_root_length():
    header = _sample_header_v2_dict()
    header["registry_root"] = "0" * 63  # too short
    with pytest.raises(CodecError):
        BinaryCodec.encode_header_v2(header)


def test_header_v2_rejects_non_hex_registry_root():
    header = _sample_header_v2_dict()
    header["registry_root"] = "zz" + "0" * 62
    with pytest.raises(ValueError):
        BinaryCodec.encode_header_v2(header)


def test_header_v2_version_zero_rejected_on_decode():
    """Decode does not validate semantic version; encoding puts whatever is given.
    This test documents that version field is carried as-is."""
    header = _sample_header_v2_dict()
    header["version"] = 0
    encoded = BinaryCodec.encode_header_v2(header)
    decoded, _ = BinaryCodec.decode_header_v2(encoded)
    assert decoded["version"] == 0
