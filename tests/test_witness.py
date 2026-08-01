
import time

from chainbreaker.crypto import HashEngine
from chainbreaker.witness import (
    CuratorSigner,
    Registry,
    is_fresh,
    verify_attestation,
    verify_transaction_witnesses,
)


def make_body():
    return {
        "schema": "chainbreaker-manifest-v1",
        "content_hash": "a" * 64,
        "byte_length": 1,
        "media_type": "text/plain",
        "title": "x",
        "language": None,
        "source": None,
        "source_uri": None,
        "acquisition_date": None,
        "license": None,
        "parent_hash": None,
        "metadata_hash": "b" * 64,
        "notes_hash": None,
    }


def test_sign_verify_attestation():
    signer = CuratorSigner("alice")
    registry = Registry()
    registry.register(signer.as_curator())
    body = make_body()
    witness = signer.sign_manifest(body)
    assert verify_attestation(registry, witness, HashEngine.hash_object_hex(body), 1)


def test_unknown_curator_fails():
    signer = CuratorSigner("alice")
    registry = Registry()
    body = make_body()
    witness = signer.sign_manifest(body)
    assert not verify_attestation(registry, witness, HashEngine.hash_object_hex(body), 1)


def test_signature_tampering_fails():
    signer = CuratorSigner("alice")
    registry = Registry()
    registry.register(signer.as_curator())
    body = make_body()
    witness = signer.sign_manifest(body)
    witness["signature"] = "0" * 128
    assert not verify_attestation(registry, witness, HashEngine.hash_object_hex(body), 1)


def test_malformed_signature_returns_false():
    signer = CuratorSigner("alice")
    registry = Registry()
    registry.register(signer.as_curator())
    body = make_body()
    witness = signer.sign_manifest(body)
    witness["signature"] = "not-hex"
    assert not verify_attestation(registry, witness, HashEngine.hash_object_hex(body), 1)


def test_revoked_key_fails():
    signer = CuratorSigner("alice")
    registry = Registry()
    registry.register(signer.as_curator(revocation_height=5))
    body = make_body()
    witness = signer.sign_manifest(body)
    assert verify_attestation(registry, witness, HashEngine.hash_object_hex(body), 1)
    assert not verify_attestation(registry, witness, HashEngine.hash_object_hex(body), 5)


def test_duplicate_curator_witnesses_rejected():
    signer = CuratorSigner("alice")
    registry = Registry()
    registry.register(signer.as_curator())
    body = make_body()
    w = signer.sign_manifest(body)
    tx = {"version": 1, "type": "scripture", "body": body, "witnesses": [w, w]}
    assert not verify_transaction_witnesses(registry, tx, 1)


def test_freshness_check():
    w = {"curator_id": "a", "timestamp": int(time.time()), "signature": "0" * 128}
    assert is_fresh(w)
    w["timestamp"] -= 100000
    assert not is_fresh(w)


def test_historical_attestation_does_not_expire():
    signer = CuratorSigner("alice")
    registry = Registry()
    registry.register(signer.as_curator())
    body = make_body()
    # Witness from long ago
    witness = signer.sign_manifest(body, timestamp=1000)
    # Freshness check would fail
    assert not is_fresh(witness, now=2000000)
    # But cryptographic/historical validity still passes
    assert verify_attestation(registry, witness, HashEngine.hash_object_hex(body), 1)
