
import pytest

from chainbreaker.codec import (
    BinaryCodec,
    CodecError,
    SchemaError,
    validate_scripture_body,
    validate_transaction,
    validate_v2_transaction,
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


# ---------------------------------------------------------------------------
# V2 governance network_id structural validation
# ---------------------------------------------------------------------------

def _make_v2_governance_body(network_id: str | None = "chainbreaker-scripture-v2") -> dict:
    """Return a structurally valid V2 governance body with mutable network_id."""
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": "a" * 64,
        "activation_height": 1,
        "previous_registry_root": "b" * 64,
        "schema_version": 1,
        "governance_signatures": [{"key_index": 0, "signature": "c" * 128}],
    }
    if network_id is not None:
        body["network_id"] = network_id
    return body


def test_validate_v2_transaction_accepts_alpha_network_id():
    """Alpha network ID must still be structurally accepted."""
    body = _make_v2_governance_body("chainbreaker-scripture-v2")
    tx = {"type": "governance", "body": body}
    validate_v2_transaction(tx)


def test_validate_v2_transaction_accepts_non_alpha_network_id():
    """A valid non-alpha network ID must be structurally accepted by the codec."""
    body = _make_v2_governance_body("test-network-v1")
    tx = {"type": "governance", "body": body}
    validate_v2_transaction(tx)


def test_validate_v2_transaction_rejects_empty_network_id():
    """Empty string network_id must fail structural validation."""
    body = _make_v2_governance_body("")
    tx = {"type": "governance", "body": body}
    with pytest.raises(SchemaError, match="network_id must be a non-empty string"):
        validate_v2_transaction(tx)


def test_validate_v2_transaction_rejects_non_string_network_id():
    """Non-string network_id must fail structural validation."""
    body = _make_v2_governance_body(12345)  # type: ignore[arg-type]
    tx = {"type": "governance", "body": body}
    with pytest.raises(SchemaError, match="network_id must be a non-empty string"):
        validate_v2_transaction(tx)


def test_validate_v2_transaction_rejects_missing_network_id():
    """Missing network_id must fail structural validation (required_base)."""
    body = _make_v2_governance_body(network_id=None)
    tx = {"type": "governance", "body": body}
    with pytest.raises(SchemaError, match="governance body missing required base fields"):
        validate_v2_transaction(tx)
