"""Tests for historical attestation validation (Milestone 4E).

These tests verify that curator signatures are evaluated against the registry
state at the attestation's block height, not the current ledger state.
"""

from chainbreaker.chain import Ledger
from chainbreaker.crypto import HashEngine, encode_public_key, generate_keypair, sign
from chainbreaker.governance import (
    NETWORK_ID,
    GovernanceSignature,
)
from chainbreaker.registry_state import registry_root
from chainbreaker.witness import (
    CuratorSigner,
    sign_attestation_v2,
    verify_attestation_v2,
    verify_transaction_witnesses_v2,
)


def _make_governance_keys(count: int = 3, threshold: int = 2):
    pairs = [generate_keypair() for _ in range(count)]
    privs = [p[0] for p in pairs]
    pubs = [encode_public_key(p[1]) for p in pairs]
    return privs, pubs


def _sign_body(privs, body: dict) -> list[dict]:
    message = HashEngine.hash_object({
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body),
    })
    return [GovernanceSignature(i, sign(priv, message)).to_dict() for i, priv in enumerate(privs)]


def _archive_tx(body: dict, witnesses: list[dict]) -> dict:
    return {
        "version": 1,
        "type": "scripture",
        "body": body,
        "witnesses": witnesses,
    }


def test_valid_historical_attestation():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    curator = CuratorSigner("alice")

    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": curator.public_key_hex,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    tx = {"type": "governance", "body": {**body, "governance_signatures": _sign_body(privs, body)}}
    block1 = ledger.mine_block_v2([tx])
    assert ledger.add_block_v2(block1)

    state = ledger.registry_state_at(1)
    body_hash = "a" * 64
    witness = sign_attestation_v2(curator.sk, body_hash, "alice", 2)
    witness["public_key_hex"] = curator.public_key_hex
    assert verify_attestation_v2(state, witness, body_hash, 2)


def test_pre_activation_signature_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    curator = CuratorSigner("alice")

    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": curator.public_key_hex,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    tx = {"type": "governance", "body": {**body, "governance_signatures": _sign_body(privs, body)}}
    block1 = ledger.mine_block_v2([tx])
    assert ledger.add_block_v2(block1)

    state = ledger.registry_state_at(1)
    body_hash = "a" * 64
    witness = sign_attestation_v2(curator.sk, body_hash, "alice", 1)
    witness["public_key_hex"] = curator.public_key_hex
    assert not verify_attestation_v2(state, witness, body_hash, 1)


def test_unknown_curator_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    curator = CuratorSigner("bob")

    state = ledger.registry_state_at(0)
    body_hash = "a" * 64
    witness = sign_attestation_v2(curator.sk, body_hash, "bob", 1)
    witness["public_key_hex"] = curator.public_key_hex
    assert not verify_attestation_v2(state, witness, body_hash, 1)


def test_post_revocation_signature_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    curator = CuratorSigner("alice")

    register_body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": curator.public_key_hex,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    tx1 = {"type": "governance", "body": {**register_body, "governance_signatures": _sign_body(privs, register_body)}}
    block1 = ledger.mine_block_v2([tx1])
    assert ledger.add_block_v2(block1)

    revoke_body = {
        "action": "curator_revoke",
        "curator_id": "alice",
        "public_key_hex": curator.public_key_hex,
        "revocation_height": 3,
        "reason_code": "compromised",
        "previous_registry_root": registry_root(ledger.registry_state_at(1)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    message = HashEngine.hash_object({
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(revoke_body),
    })
    gov_sigs = _sign_body(privs, revoke_body)
    curator_sig = sign(curator.sk, message)
    tx2 = {"type": "governance", "body": {**revoke_body, "governance_signatures": gov_sigs, "curator_signature": curator_sig}}
    block2 = ledger.mine_block_v2([tx2])
    assert ledger.add_block_v2(block2)

    state2 = ledger.registry_state_at(2)
    body_hash = "a" * 64
    witness = sign_attestation_v2(curator.sk, body_hash, "alice", 2)
    witness["public_key_hex"] = curator.public_key_hex
    assert verify_attestation_v2(state2, witness, body_hash, 2)
    assert not verify_attestation_v2(state2, witness, body_hash, 3)


def test_rotation_boundary():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    old_curator = CuratorSigner("alice")
    new_curator = CuratorSigner("alice")  # same id, new key

    register_body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": old_curator.public_key_hex,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    tx1 = {"type": "governance", "body": {**register_body, "governance_signatures": _sign_body(privs, register_body)}}
    block1 = ledger.mine_block_v2([tx1])
    assert ledger.add_block_v2(block1)

    rotate_body = {
        "action": "curator_rotate",
        "curator_id": "alice",
        "public_key_hex": old_curator.public_key_hex,
        "new_public_key_hex": new_curator.public_key_hex,
        "activation_height": 3,
        "previous_registry_root": registry_root(ledger.registry_state_at(1)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    # Rotation requires curator signature with old key + governance signatures
    message = HashEngine.hash_object({
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(rotate_body),
    })
    gov_sigs = _sign_body(privs, rotate_body)
    curator_sig = sign(old_curator.sk, message)
    tx2 = {"type": "governance", "body": {**rotate_body, "governance_signatures": gov_sigs, "curator_signature": curator_sig}}
    block2 = ledger.mine_block_v2([tx2])
    assert ledger.add_block_v2(block2)

    state2 = ledger.registry_state_at(2)
    body_hash = "a" * 64
    old_witness = sign_attestation_v2(old_curator.sk, body_hash, "alice", 2)
    old_witness["public_key_hex"] = old_curator.public_key_hex
    new_witness = sign_attestation_v2(new_curator.sk, body_hash, "alice", 3)
    new_witness["public_key_hex"] = new_curator.public_key_hex

    assert verify_attestation_v2(state2, old_witness, body_hash, 2)
    assert not verify_attestation_v2(state2, old_witness, body_hash, 3)
    assert not verify_attestation_v2(state2, new_witness, body_hash, 2)
    assert verify_attestation_v2(state2, new_witness, body_hash, 3)


def test_malformed_witness_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    state = ledger.registry_state_at(0)
    body_hash = "a" * 64
    assert not verify_attestation_v2(state, {}, body_hash, 1)
    assert not verify_attestation_v2(state, {"curator_id": "x", "signature": "y", "block_height": 1, "public_key_hex": "z"}, body_hash, 1)


def test_wrong_block_height_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    curator = CuratorSigner("alice")

    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": curator.public_key_hex,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    tx = {"type": "governance", "body": {**body, "governance_signatures": _sign_body(privs, body)}}
    block1 = ledger.mine_block_v2([tx])
    assert ledger.add_block_v2(block1)

    state = ledger.registry_state_at(1)
    body_hash = "a" * 64
    witness = sign_attestation_v2(curator.sk, body_hash, "alice", 2)
    witness["public_key_hex"] = curator.public_key_hex
    assert not verify_attestation_v2(state, witness, body_hash, 3)


def test_transaction_witnesses_v2_requires_min_attestations():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    curator = CuratorSigner("alice")

    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": curator.public_key_hex,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    tx = {"type": "governance", "body": {**body, "governance_signatures": _sign_body(privs, body)}}
    block1 = ledger.mine_block_v2([tx])
    assert ledger.add_block_v2(block1)

    state = ledger.registry_state_at(1)
    archive = _archive_tx({"name": "doc1"}, [])
    body_hash = HashEngine.hash_object_hex(archive["body"])
    witness = sign_attestation_v2(curator.sk, body_hash, "alice", 2)
    witness["public_key_hex"] = curator.public_key_hex
    archive["witnesses"] = [witness]
    assert verify_transaction_witnesses_v2(state, archive, 2, min_attestations=1)
    assert not verify_transaction_witnesses_v2(state, archive, 2, min_attestations=2)


def test_two_independent_processes_identical_validation():
    privs, pubs = _make_governance_keys()
    curator_sk, curator_pk = generate_keypair()
    curator_pub = encode_public_key(curator_pk)

    def build():
        ledger = Ledger(governance_keys=pubs, governance_threshold=2)
        body = {
            "action": "curator_register",
            "curator_id": "alice",
            "public_key_hex": curator_pub,
            "activation_height": 2,
            "previous_registry_root": registry_root(ledger.registry_state_at(0)),
            "network_id": NETWORK_ID,
            "schema_version": 1,
        }
        tx = {"type": "governance", "body": {**body, "governance_signatures": _sign_body(privs, body)}}
        block1 = ledger.mine_block_v2([tx])
        assert ledger.add_block_v2(block1)
        return ledger

    ledger1 = build()
    ledger2 = build()

    body_hash = "a" * 64
    witness = sign_attestation_v2(curator_sk, body_hash, "alice", 2)
    witness["public_key_hex"] = curator_pub
    assert verify_attestation_v2(ledger1.registry_state_at(1), witness, body_hash, 2)
    assert verify_attestation_v2(ledger2.registry_state_at(1), witness, body_hash, 2)
