
import pytest

from chainbreaker.codec import (
    BinaryCodec,
    CodecError,
    validate_scripture_body,
    validate_transaction,
)


def make_scripture_body():
    return {
        "schema": "chainbreaker-manifest-v1",
        "content_hash": "a" * 64,
        "byte_length": 100,
        "media_type": "text/plain",
        "title": "T",
        "language": "en",
        "source": "src",
        "source_uri": None,
        "acquisition_date": 1704067200,
        "license": "PD",
        "parent_hash": None,
        "metadata_hash": "b" * 64,
        "notes_hash": None,
    }


def test_header_roundtrip():
    header = {
        "version": 1,
        "prev_hash": "0" * 64,
        "merkle_root": "a" * 64,
        "timestamp": 1704067200,
        "target": "0" * 63 + "1",
        "nonce": 12345,
    }
    data = BinaryCodec.encode_header(header)
    decoded, offset = BinaryCodec.decode_header(data)
    assert decoded == header
    assert offset == len(data)


def test_transaction_roundtrip():
    tx = {
        "version": 1,
        "type": "scripture",
        "body": make_scripture_body(),
        "witnesses": [],
    }
    data = BinaryCodec.encode_transaction(tx)
    decoded, offset = BinaryCodec.decode_transaction(data)
    assert decoded == tx
    assert offset == len(data)


def test_decode_header_truncated():
    with pytest.raises(CodecError):
        BinaryCodec.decode_header(BinaryCodec.encode_header({"version": 1, "prev_hash": "0"*64})[:50])


def test_decode_transaction_truncated():
    tx = {"version": 1, "type": "scripture", "body": make_scripture_body(), "witnesses": []}
    data = BinaryCodec.encode_transaction(tx)
    with pytest.raises(CodecError):
        BinaryCodec.decode_transaction(data[:-3])


def test_invalid_hash_length():
    header = {
        "version": 1,
        "prev_hash": "0" * 63,
        "merkle_root": "a" * 64,
        "timestamp": 1704067200,
        "target": "0" * 64,
        "nonce": 0,
    }
    with pytest.raises(CodecError):
        BinaryCodec.encode_header(header)


def test_validate_transaction_ok():
    tx = {
        "version": 1,
        "type": "scripture",
        "body": make_scripture_body(),
        "witnesses": [],
    }
    validate_transaction(tx)


def test_validate_transaction_bad_type():
    tx = {
        "version": 1,
        "type": "badtype",
        "body": make_scripture_body(),
        "witnesses": [],
    }
    with pytest.raises(ValueError):
        validate_transaction(tx)


def test_validate_transaction_float_rejected():
    body = make_scripture_body()
    body["byte_length"] = 1.5
    tx = {"version": 1, "type": "scripture", "body": body, "witnesses": []}
    with pytest.raises(ValueError):
        validate_transaction(tx)


def test_validate_scripture_bad_hash():
    body = make_scripture_body()
    body["content_hash"] = "GGGG"
    with pytest.raises(ValueError):
        validate_scripture_body(body)
