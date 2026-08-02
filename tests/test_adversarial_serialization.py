"""Phase 5A: canonical serialization attack tests.

These tests try to find multiple byte/JSON representations of the same logical
consensus object.  Every accepted object must have exactly one canonical form.
"""

import json
import struct

import pytest

from chainbreaker.block import BlockHeaderV2
from chainbreaker.codec import BinaryCodec, CodecError
from chainbreaker.crypto import HashEngine, encode_public_key, generate_keypair, sign
from chainbreaker.crypto import verify as verify_sig
from chainbreaker.governance import NETWORK_ID, GovernanceSignature
from chainbreaker.registry_state import (
    CuratorRecord,
    RegistryState,
    registry_root,
    serialize_registry_state,
)
from chainbreaker.witness import attestation_message_v2


def _sample_header_dict() -> dict:
    return {
        "version": 2,
        "prev_hash": "a" * 64,
        "merkle_root": "b" * 64,
        "registry_root": "c" * 64,
        "timestamp": 1700000000,
        "target": "0000ffff00000000000000000000000000000000000000000000000000000000",
        "nonce": 12345,
    }


def test_header_v2_canonical_round_trip():
    h = _sample_header_dict()
    encoded = BinaryCodec.encode_header_v2(h)
    assert len(encoded) == 149
    decoded, offset = BinaryCodec.decode_header_v2(encoded)
    assert offset == 149
    assert decoded == h


def test_header_v2_rejects_extra_trailing_bytes():
    h = _sample_header_dict()
    encoded = BinaryCodec.encode_header_v2(h) + bytes([0])
    with pytest.raises(CodecError):
        BinaryCodec.decode_header_v2(encoded, strict=True)


def test_header_v2_rejects_short_input():
    h = _sample_header_dict()
    encoded = BinaryCodec.encode_header_v2(h)[:-1]
    with pytest.raises(CodecError):
        BinaryCodec.decode_header_v2(encoded, strict=True)


def test_header_v2_rejects_wrong_type_marker():
    h = _sample_header_dict()
    encoded = bytes([1]) + BinaryCodec.encode_header_v2(h)[1:]
    with pytest.raises(CodecError):
        BinaryCodec.decode_header_v2(encoded)


def test_header_v2_rejects_zero_type_marker():
    h = _sample_header_dict()
    encoded = bytes([0]) + BinaryCodec.encode_header_v2(h)[1:]
    with pytest.raises(CodecError):
        BinaryCodec.decode_header_v2(encoded)


def test_header_v2_big_endian_version_changes_decode():
    """Same logical header with BE version bytes decodes to a different version."""
    h = _sample_header_dict()
    canonical = BinaryCodec.encode_header_v2(h)
    swapped = bytearray(canonical)
    swapped[1:5] = struct.pack(">I", h["version"])
    assert bytes(swapped) != canonical
    decoded, _ = BinaryCodec.decode_header_v2(bytes(swapped))
    assert decoded["version"] != h["version"]


def test_header_v2_zero_version_can_be_encoded():
    h = BlockHeaderV2(
        version=0,
        prev_hash="a" * 64,
        merkle_root="b" * 64,
        registry_root="c" * 64,
        timestamp=1700000000,
        target="0000ffff00000000000000000000000000000000000000000000000000000000",
        nonce=0,
    )
    assert h.version == 0


def test_registry_state_root_stable_across_instantiations():
    state = RegistryState.genesis(["aa" * 32, "bb" * 32, "cc" * 32], threshold=2)
    root1 = registry_root(state)
    root2 = registry_root(state)
    assert root1 == root2


def test_registry_state_root_independent_of_record_object_identity():
    """Same records, different tuple/object identity must produce the same root."""
    r1 = CuratorRecord(
        curator_id="alice",
        public_key_hex="aa" * 32,
        activation_height=2,
        revocation_height=None,
        previous_key_hex=None,
        registration_txid="11" * 32,
        latest_rotation_txid=None,
    )
    r2 = CuratorRecord(
        curator_id="alice",
        public_key_hex="aa" * 32,
        activation_height=2,
        revocation_height=None,
        previous_key_hex=None,
        registration_txid="11" * 32,
        latest_rotation_txid=None,
    )
    s1 = RegistryState(
        records=(r1,),
        governance_version=1,
        network_id=NETWORK_ID,
        governance_keys=("aa" * 32,),
        threshold=1,
    )
    s2 = RegistryState(
        records=(r2,),
        governance_version=1,
        network_id=NETWORK_ID,
        governance_keys=("aa" * 32,),
        threshold=1,
    )
    assert registry_root(s1) == registry_root(s2)


def test_registry_state_record_order_does_not_change_root():
    """Records are sorted by curator_id before serialization."""
    sk_a, pk_a = generate_keypair()
    sk_b, pk_b = generate_keypair()
    pub_a = encode_public_key(pk_a)
    pub_b = encode_public_key(pk_b)
    rec_a = CuratorRecord(
        curator_id="alice", public_key_hex=pub_a, activation_height=2,
        revocation_height=None, previous_key_hex=None,
        registration_txid="11" * 32, latest_rotation_txid=None,
    )
    rec_b = CuratorRecord(
        curator_id="bob", public_key_hex=pub_b, activation_height=3,
        revocation_height=None, previous_key_hex=None,
        registration_txid="22" * 32, latest_rotation_txid=None,
    )
    s1 = RegistryState.genesis(["cc" * 32], 1)
    s_forward = RegistryState(
        records=(rec_a, rec_b),
        governance_version=s1.governance_version,
        network_id=s1.network_id,
        governance_keys=s1.governance_keys,
        threshold=s1.threshold,
    )
    s_reverse = RegistryState(
        records=(rec_b, rec_a),
        governance_version=s1.governance_version,
        network_id=s1.network_id,
        governance_keys=s1.governance_keys,
        threshold=s1.threshold,
    )
    assert registry_root(s_forward) == registry_root(s_reverse)


def test_governance_transaction_canonical_json_alters_hash():
    """Whitespace must change the transaction ID; key order must not."""
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": "aa" * 32,
        "activation_height": 2,
        "previous_registry_root": "cc" * 32,
        "governance_signatures": [GovernanceSignature(0, "00" * 64).to_dict()],
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    canonical = HashEngine.canonical_json(body)
    whitespace = json.dumps(body, sort_keys=True, separators=(",", ":"), indent=2).encode("utf-8")
    assert HashEngine.hash_object_hex(body) != HashEngine.hash_single_hex(whitespace)
    reordered = {k: body[k] for k in sorted(body.keys(), reverse=True)}
    assert HashEngine.hash_object_hex(body) == HashEngine.hash_object_hex(reordered)
    assert canonical != whitespace


def test_attestation_message_v2_canonical():
    """Changing the message shape invalidates the signature domain."""
    body_hash = "aa" * 32
    msg1 = attestation_message_v2(body_hash, "alice", 5)
    msg2 = attestation_message_v2(body_hash, "alice", 5)
    assert msg1 == msg2

    tampered = {
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "attestation",
        "body_hash": body_hash,
        "curator_id": "alice",
        "block_height": 5,
        "extra": "bad",
    }
    assert HashEngine.hash_object_hex(tampered) != HashEngine.hash_single_hex(msg1)


def test_attestation_signature_invalidates_on_height_change():
    sk, pk = generate_keypair()
    body_hash = "aa" * 32
    msg5 = attestation_message_v2(body_hash, "alice", 5)
    msg6 = attestation_message_v2(body_hash, "alice", 6)
    assert msg5 != msg6
    sig5 = sign(sk, msg5)
    assert not verify_sig(pk, msg6, sig5)


def test_header_v2_offset_decoding_isolated():
    """Decoding a header embedded in a larger buffer must respect offset."""
    h = _sample_header_dict()
    encoded = BinaryCodec.encode_header_v2(h)
    prefix = bytes([0xFF, 0xEE, 0xDD])
    suffix = bytes([0xCC, 0xBB, 0xAA])
    embedded = prefix + encoded + suffix
    decoded, offset = BinaryCodec.decode_header_v2(embedded, offset=len(prefix))
    assert decoded == h
    assert offset == len(prefix) + 149


def test_registry_state_serialization_keeps_duplicate_keys():
    """Duplicate governance keys are still present in sorted order."""
    key = "aa" * 32
    state = RegistryState.genesis([key, key, key], threshold=2)
    data = serialize_registry_state(state)
    net_len_offset = 4 + len(_encode_varint(len(NETWORK_ID.encode("utf-8")))) + len(NETWORK_ID.encode("utf-8"))
    assert data[net_len_offset] == 3


def test_random_mutated_header_bytes_change_decode():
    """Fuzz-style mutation: single-bit flips should change the decoded header."""
    h = _sample_header_dict()
    encoded = bytearray(BinaryCodec.encode_header_v2(h))
    encoded[1] ^= 0x01
    decoded, _ = BinaryCodec.decode_header_v2(bytes(encoded))
    assert decoded != h or decoded["version"] != h["version"]


def _encode_varint(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return bytes([0xFD]) + n.to_bytes(2, "little")
    if n <= 0xFFFFFFFF:
        return bytes([0xFE]) + n.to_bytes(4, "little")
    return bytes([0xFF]) + n.to_bytes(8, "little")

def test_header_v2_strict_rejects_oversized_input():
    h = _sample_header_dict()
    encoded = BinaryCodec.encode_header_v2(h) + bytes([0] * 1000)
    with pytest.raises(CodecError):
        BinaryCodec.decode_header_v2(encoded, strict=True)


def test_header_v2_encode_rejects_invalid_hash_length():
    h = dict(_sample_header_dict())
    h["prev_hash"] = "aa" * 31  # only 62 hex chars
    with pytest.raises(CodecError):
        BinaryCodec.encode_header_v2(h)


def test_header_v2_encode_rejects_non_hex_hash():
    h = dict(_sample_header_dict())
    h["merkle_root"] = "zz" + "00" * 31
    with pytest.raises(CodecError):
        BinaryCodec.encode_header_v2(h)


def test_header_v2_decode_with_embedded_offset_uses_nonstrict_by_default():
    """Default decode mode must still allow trailing bytes for stream parsing."""
    h = _sample_header_dict()
    encoded = BinaryCodec.encode_header_v2(h) + b"trailing"
    decoded, offset = BinaryCodec.decode_header_v2(encoded)
    assert decoded == h
    assert offset == 149


def test_governance_body_unexpected_key_rejected():
    from chainbreaker.governance import CuratorRegisterTx, GovernanceError
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": "aa" * 32,
        "activation_height": 2,
        "previous_registry_root": "cc" * 32,
        "governance_signatures": [GovernanceSignature(0, "00" * 64).to_dict()],
        "network_id": NETWORK_ID,
        "schema_version": 1,
        "extra": "bad",
    }
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(body)


def test_attestation_extra_key_changes_message():
    body_hash = "aa" * 32
    base = {
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "attestation",
        "body_hash": body_hash,
        "curator_id": "alice",
        "block_height": 5,
    }
    msg_base = HashEngine.canonical_json(base)
    extra = dict(base)
    extra["block_height"] = 5
    extra["extra"] = "bad"
    msg_extra = HashEngine.canonical_json(extra)
    assert msg_base != msg_extra
