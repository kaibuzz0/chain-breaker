
import pytest

from chainbreaker.codec import BinaryCodec, CodecError


def test_header_roundtrip():
    header = {
        "version": 1,
        "prev_hash": "0" * 64,
        "merkle_root": "a" * 64,
        "timestamp": 1704067200,
        "difficulty": 16,
        "nonce": 12345,
    }
    data = BinaryCodec.encode_header(header)
    decoded, offset = BinaryCodec.decode_header(data)
    assert decoded == header


def test_oversized_hash_rejected():
    with pytest.raises(CodecError):
        BinaryCodec.encode_hash("a" * 66)


def test_truncated_header_rejected():
    with pytest.raises(CodecError):
        BinaryCodec.decode_header(b"\x02" + b"\x00" * 5)
