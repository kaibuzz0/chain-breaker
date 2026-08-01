"""Tests for governance transaction models."""

import pytest

from chainbreaker.crypto import encode_public_key, generate_keypair
from chainbreaker.governance import (
    NETWORK_ID,
    CuratorRegisterTx,
    CuratorRevokeTx,
    CuratorRotateTx,
    GovernanceContext,
    GovernanceError,
    GovernanceSignature,
    governance_message,
)


def _keypair():
    sk, pk = generate_keypair()
    return sk, encode_public_key(pk)


def _gov_context(n=1, threshold=1):
    keys = [_keypair() for _ in range(n)]
    ctx = GovernanceContext([pk for _, pk in keys], threshold=threshold)
    return ctx, keys

def test_empty_signature_rejected():
    with pytest.raises(GovernanceError):
        GovernanceSignature.from_dict({})


def test_signature_bad_keys():
    with pytest.raises(GovernanceError):
        GovernanceSignature.from_dict({"key_index": 0, "signature": "aa"})


def test_signature_valid():
    sig = GovernanceSignature(key_index=0, signature_hex="a" * 128)
    d = sig.to_dict()
    assert d["key_index"] == 0
    assert d["signature"] == "a" * 128
    restored = GovernanceSignature.from_dict(d)
    assert restored.key_index == 0


def test_register_roundtrip():
    sk, pk = _keypair()
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": pk,
        "activation_height": 5,
        "previous_registry_root": "0" * 64,
        "governance_signatures": [],
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    tx = CuratorRegisterTx.from_dict(body)
    assert tx.curator_id == "alpha"
    assert tx.public_key_hex == pk
    assert tx.activation_height == 5
    d = tx.to_dict()
    assert d["action"] == "curator_register"
    assert d["network_id"] == "chainbreaker-scripture-v2"


def test_register_wrong_network():
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": "a" * 64,
        "activation_height": 5,
        "previous_registry_root": "0" * 64,
        "governance_signatures": [],
        "network_id": "wrong",
    }
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(body)


def test_register_bad_schema_version():
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": "a" * 64,
        "activation_height": 5,
        "previous_registry_root": "0" * 64,
        "governance_signatures": [],
        "schema_version": 99,
    }
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(body)


def test_register_invalid_key_length():
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": "a" * 63,
        "activation_height": 5,
        "previous_registry_root": "0" * 64,
        "governance_signatures": [],
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(body)


def test_register_invalid_curator_id_empty():
    body = {
        "action": "curator_register",
        "curator_id": "",
        "public_key_hex": "a" * 64,
        "activation_height": 5,
        "previous_registry_root": "0" * 64,
        "governance_signatures": [],
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(body)


def test_register_invalid_curator_id_too_long():
    body = {
        "action": "curator_register",
        "curator_id": "x" * 200,
        "public_key_hex": "a" * 64,
        "activation_height": 5,
        "previous_registry_root": "0" * 64,
        "governance_signatures": [],
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(body)


def test_register_negative_activation():
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": "a" * 64,
        "activation_height": -1,
        "previous_registry_root": "0" * 64,
        "governance_signatures": [],
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(body)


def test_rotate_roundtrip():
    sk, pk = _keypair()
    _, pk2 = _keypair()
    body = {
        "action": "curator_rotate",
        "curator_id": "alpha",
        "public_key_hex": pk,
        "new_public_key_hex": pk2,
        "activation_height": 10,
        "previous_registry_root": "0" * 64,
        "governance_signatures": [],
        "curator_signature": "b" * 128,
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    tx = CuratorRotateTx.from_dict(body)
    assert tx.public_key_hex == pk
    assert tx.new_public_key_hex == pk2


def test_rotate_bad_signature_length():
    body = {
        "action": "curator_rotate",
        "curator_id": "alpha",
        "public_key_hex": "a" * 64,
        "new_public_key_hex": "b" * 64,
        "activation_height": 10,
        "previous_registry_root": "0" * 64,
        "governance_signatures": [],
        "curator_signature": "cc",
    }
    with pytest.raises(GovernanceError):
        CuratorRotateTx.from_dict(body)


def test_revoke_roundtrip():
    body = {
        "action": "curator_revoke",
        "curator_id": "alpha",
        "public_key_hex": "a" * 64,
        "revocation_height": 10,
        "reason_code": "compromise",
        "previous_registry_root": "0" * 64,
        "governance_signatures": [],
        "curator_signature": "b" * 128,
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    tx = CuratorRevokeTx.from_dict(body)
    assert tx.reason_code == "compromise"


def test_revoke_reason_too_long():
    body = {
        "action": "curator_revoke",
        "curator_id": "alpha",
        "public_key_hex": "a" * 64,
        "revocation_height": 10,
        "reason_code": "x" * 100,
        "previous_registry_root": "0" * 64,
        "governance_signatures": [],
        "curator_signature": "b" * 128,
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    with pytest.raises(GovernanceError):
        CuratorRevokeTx.from_dict(body)


def test_governance_message_deterministic():
    body = {"action": "curator_register", "curator_id": "alpha"}
    m1 = governance_message(body)
    m2 = governance_message(body)
    assert m1 == m2



def test_governance_signature_validation_errors():
    """Cover error paths in GovernanceSignature.from_dict."""
    with pytest.raises(GovernanceError):
        GovernanceSignature.from_dict("not a dict")
    with pytest.raises(GovernanceError):
        GovernanceSignature.from_dict({"signature": "aa" * 64})
    with pytest.raises(GovernanceError):
        GovernanceSignature.from_dict({"key_index": -1, "signature": "aa" * 64})
    with pytest.raises(GovernanceError):
        GovernanceSignature.from_dict({"key_index": 0, "signature": "not hex"})


def test_curator_register_body_validation_errors():
    sk, pk = _keypair()
    base = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": pk,
        "activation_height": 5,
        "previous_registry_root": "00" * 32,
        "network_id": NETWORK_ID,
        "schema_version": 1,
        "governance_signatures": [],
    }
    # wrong action
    bad = dict(base, action="other")
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(bad)
    # wrong network_id
    bad = dict(base, network_id="other")
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(bad)
    # bad schema
    bad = dict(base, schema_version=99)
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(bad)
    # not a dict
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict("x")
    # unexpected keys
    bad = dict(base, extra="x")
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(bad)
    # invalid curator_id type
    bad = dict(base, curator_id=123)
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(bad)
    # invalid activation height type
    bad = dict(base, activation_height="5")
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(bad)
    # invalid previous_registry_root
    bad = dict(base, previous_registry_root="gg")
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(bad)
    # signatures not a list
    bad = dict(base, governance_signatures="x")
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(bad)


def test_curator_rotate_body_validation_errors():
    sk, pk = _keypair()
    new_sk, new_pk = _keypair()
    base = {
        "action": "curator_rotate",
        "curator_id": "alpha",
        "public_key_hex": pk,
        "new_public_key_hex": new_pk,
        "activation_height": 10,
        "previous_registry_root": "00" * 32,
        "network_id": NETWORK_ID,
        "schema_version": 1,
        "governance_signatures": [],
        "curator_signature": "aa" * 32,
    }
    bad = dict(base, action="other")
    with pytest.raises(GovernanceError):
        CuratorRotateTx.from_dict(bad)
    bad = dict(base, network_id="other")
    with pytest.raises(GovernanceError):
        CuratorRotateTx.from_dict(bad)
    bad = dict(base, schema_version=99)
    with pytest.raises(GovernanceError):
        CuratorRotateTx.from_dict(bad)
    with pytest.raises(GovernanceError):
        CuratorRotateTx.from_dict("x")
    bad = dict(base, extra="x")
    with pytest.raises(GovernanceError):
        CuratorRotateTx.from_dict(bad)



def test_curator_revoke_body_validation_errors():
    sk, pk = _keypair()
    base = {
        "action": "curator_revoke",
        "curator_id": "alpha",
        "public_key_hex": pk,
        "revocation_height": 20,
        "reason_code": "compromise",
        "previous_registry_root": "00" * 32,
        "network_id": NETWORK_ID,
        "schema_version": 1,
        "governance_signatures": [],
        "curator_signature": "aa" * 32,
    }
    bad = dict(base, action="other")
    with pytest.raises(GovernanceError):
        CuratorRevokeTx.from_dict(bad)
    bad = dict(base, network_id="other")
    with pytest.raises(GovernanceError):
        CuratorRevokeTx.from_dict(bad)
    bad = dict(base, schema_version=99)
    with pytest.raises(GovernanceError):
        CuratorRevokeTx.from_dict(bad)
    with pytest.raises(GovernanceError):
        CuratorRevokeTx.from_dict("x")
    bad = dict(base, extra="x")
    with pytest.raises(GovernanceError):
        CuratorRevokeTx.from_dict(bad)
    # empty reason code
    bad = dict(base, reason_code="")
    with pytest.raises(GovernanceError):
        CuratorRevokeTx.from_dict(bad)


def test_governance_context_validation():
    sk, pk = _keypair()
    with pytest.raises(GovernanceError):
        GovernanceContext([], threshold=0)
    with pytest.raises(GovernanceError):
        GovernanceContext([pk], threshold=0)
    with pytest.raises(GovernanceError):
        GovernanceContext([pk, pk], threshold=1)  # duplicate
    with pytest.raises(GovernanceError):
        GovernanceContext(["not hex"], threshold=1)
    with pytest.raises(GovernanceError):
        GovernanceContext([pk], threshold=2)


def test_malformed_signature_in_verify():
    """Cover except branch in verify_governance_signatures."""
    ctx, keys = _gov_context(n=1, threshold=1)
    sig = GovernanceSignature(key_index=0, signature_hex="00" * 64)
    body = {"action": "curator_register", "curator_id": "x"}
    with pytest.raises(GovernanceError):
        ctx.verify_governance_signatures(body, [sig])



def test_signature_key_index_type_validation():
    with pytest.raises(GovernanceError, match="key_index must be an integer"):
        GovernanceSignature.from_dict({"key_index": "0", "signature": "aa" * 64})
    with pytest.raises(GovernanceError, match="key_index must be an integer"):
        GovernanceSignature.from_dict({"key_index": True, "signature": "aa" * 64})


def test_signature_must_be_string():
    with pytest.raises(GovernanceError, match="signature must be a string"):
        GovernanceSignature.from_dict({"key_index": 0, "signature": b"bytes"})


def test_hex_hash_require_string():
    from chainbreaker.governance import _require_hex_hash
    with pytest.raises(GovernanceError, match="must be a string"):
        _require_hex_hash(123, "field")


def test_register_display_metadata_hash_roundtrip():
    sk, pk = _keypair()
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": pk,
        "activation_height": 5,
        "previous_registry_root": "00" * 32,
        "network_id": NETWORK_ID,
        "schema_version": 1,
        "display_metadata_hash": "11" * 32,
        "governance_signatures": [],
    }
    tx = CuratorRegisterTx.from_dict(body)
    assert tx.to_dict()["display_metadata_hash"] == "11" * 32


def test_rotate_display_metadata_hash_roundtrip():
    sk, pk = _keypair()
    new_sk, new_pk = _keypair()
    body = {
        "action": "curator_rotate",
        "curator_id": "alpha",
        "public_key_hex": pk,
        "new_public_key_hex": new_pk,
        "activation_height": 10,
        "previous_registry_root": "00" * 32,
        "network_id": NETWORK_ID,
        "schema_version": 1,
        "display_metadata_hash": "11" * 32,
        "governance_signatures": [],
        "curator_signature": "aa" * 64,
    }
    tx = CuratorRotateTx.from_dict(body)
    assert tx.to_dict()["display_metadata_hash"] == "11" * 32


def test_governance_context_key_not_string():
    with pytest.raises(GovernanceError, match="governance key must be a string"):
        GovernanceContext([123], threshold=1)


def test_governance_context_key_wrong_length():
    sk, pk = _keypair()
    with pytest.raises(GovernanceError, match="governance key must be 32 bytes hex"):
        GovernanceContext([pk + "00"], threshold=1)


def test_verify_signature_invalid_key_index_type():
    ctx, keys = _gov_context(n=1, threshold=1)
    body = {"action": "curator_register", "curator_id": "x"}
    sig = GovernanceSignature(key_index="0", signature_hex="aa" * 64)
    with pytest.raises(GovernanceError, match="invalid key_index"):
        ctx.verify_governance_signatures(body, [sig])


def test_make_governance_signature_invalid_key():
    from chainbreaker.governance import make_governance_signature
    with pytest.raises(GovernanceError, match="invalid private key"):
        make_governance_signature("not a key", {"x": 1}, 0)
