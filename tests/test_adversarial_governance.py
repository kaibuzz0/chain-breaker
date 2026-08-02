"""Phase 5B: governance attack tests.

Attempt to change authority state without valid authorization.
"""

import pytest

from chainbreaker.chain import Ledger
from chainbreaker.crypto import HashEngine, encode_public_key, generate_keypair, sign
from chainbreaker.governance import (
    NETWORK_ID,
    CuratorRegisterTx,
    GovernanceError,
    GovernanceSignature,
)
from chainbreaker.registry_state import registry_root


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


def _curator_sig(curator_sk, body: dict) -> str:
    message = HashEngine.hash_object({
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body),
    })
    return sign(curator_sk, message)


def test_insufficient_governance_signatures_rejected():
    privs, pubs = _make_governance_keys(3, 2)
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    curator_sk, curator_pk = generate_keypair()
    pub = encode_public_key(curator_pk)
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": pub,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(privs[:1], body)
    tx = {"type": "governance", "body": body}
    block1 = ledger.mine_block_v2([tx])
    assert not ledger.add_block_v2(block1)


def test_duplicate_signatures_do_not_count_twice():
    privs, pubs = _make_governance_keys(3, 2)
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    curator_sk, curator_pk = generate_keypair()
    pub = encode_public_key(curator_pk)
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": pub,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    sig = _sign_body(privs[:1], body)[0]
    body["governance_signatures"] = [sig, sig]
    tx = {"type": "governance", "body": body}
    block1 = ledger.mine_block_v2([tx])
    assert not ledger.add_block_v2(block1)


def test_unknown_governance_signer_rejected():
    privs, pubs = _make_governance_keys(3, 2)
    attacker_privs, attacker_pubs = _make_governance_keys(3, 2)
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    curator_sk, curator_pk = generate_keypair()
    pub = encode_public_key(curator_pk)
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": pub,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(attacker_privs[:2], body)
    tx = {"type": "governance", "body": body}
    block1 = ledger.mine_block_v2([tx])
    assert not ledger.add_block_v2(block1)


def test_signature_mutation_rejected():
    privs, pubs = _make_governance_keys(3, 2)
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    curator_sk, curator_pk = generate_keypair()
    pub = encode_public_key(curator_pk)
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": pub,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    sigs = _sign_body(privs[:2], body)
    sigs[0]["signature"] = "00" * 64
    body["governance_signatures"] = sigs
    tx = {"type": "governance", "body": body}
    block1 = ledger.mine_block_v2([tx])
    assert not ledger.add_block_v2(block1)


def test_replayed_governance_transaction_rejected():
    privs, pubs = _make_governance_keys(3, 2)
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    curator_sk, curator_pk = generate_keypair()
    pub = encode_public_key(curator_pk)
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": pub,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(privs, body)
    tx = {"type": "governance", "body": body}
    block1 = ledger.mine_block_v2([tx])
    assert ledger.add_block_v2(block1)
    # Replay in next block: previous_registry_root no longer matches
    block2 = ledger.mine_block_v2([tx])
    assert not ledger.add_block_v2(block2)


def test_conflicting_rotation_rejected():
    """Rotating the same curator to two different keys in the same block is a conflict."""
    privs, pubs = _make_governance_keys(3, 2)
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    old_sk, old_pk = generate_keypair()
    old_pub = encode_public_key(old_pk)
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": old_pub,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(privs, body)
    tx1 = {"type": "governance", "body": body}
    assert ledger.add_block_v2(ledger.mine_block_v2([tx1]))

    new_sk1, new_pk1 = generate_keypair()
    new_sk2, new_pk2 = generate_keypair()
    rotate_body_1 = {
        "action": "curator_rotate",
        "curator_id": "alice",
        "public_key_hex": old_pub,
        "new_public_key_hex": encode_public_key(new_pk1),
        "activation_height": 3,
        "previous_registry_root": registry_root(ledger.registry_state_at(1)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    rotate_body_2 = dict(rotate_body_1)
    rotate_body_2["new_public_key_hex"] = encode_public_key(new_pk2)
    rotate_body_1["governance_signatures"] = _sign_body(privs, rotate_body_1)
    rotate_body_1["curator_signature"] = _curator_sig(old_sk, rotate_body_1)
    rotate_body_2["governance_signatures"] = _sign_body(privs, rotate_body_2)
    rotate_body_2["curator_signature"] = _curator_sig(old_sk, rotate_body_2)
    tx2 = {"type": "governance", "body": rotate_body_1}
    tx3 = {"type": "governance", "body": rotate_body_2}
    block2 = ledger.mine_block_v2([tx2, tx3])
    assert not ledger.add_block_v2(block2)


def test_duplicate_curator_ids_same_block_rejected():
    privs, pubs = _make_governance_keys(3, 2)
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk1, pk1 = generate_keypair()
    sk2, pk2 = generate_keypair()
    body1 = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": encode_public_key(pk1),
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    body2 = dict(body1)
    body2["public_key_hex"] = encode_public_key(pk2)
    body1["governance_signatures"] = _sign_body(privs, body1)
    body2["governance_signatures"] = _sign_body(privs, body2)
    tx1 = {"type": "governance", "body": body1}
    tx2 = {"type": "governance", "body": body2}
    block1 = ledger.mine_block_v2([tx1, tx2])
    assert not ledger.add_block_v2(block1)


def test_duplicate_active_keys_across_curators_rejected():
    privs, pubs = _make_governance_keys(3, 2)
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk, pk = generate_keypair()
    pub = encode_public_key(pk)
    body1 = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": pub,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    body2 = dict(body1)
    body2["curator_id"] = "bob"
    body1["governance_signatures"] = _sign_body(privs, body1)
    body2["governance_signatures"] = _sign_body(privs, body2)
    tx1 = {"type": "governance", "body": body1}
    tx2 = {"type": "governance", "body": body2}
    block1 = ledger.mine_block_v2([tx1, tx2])
    assert not ledger.add_block_v2(block1)


def test_malformed_public_key_rejected():
    privs, pubs = _make_governance_keys(3, 2)
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": "gg" * 32,  # invalid hex
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(body)


def test_invalid_activation_height_rejected():
    privs, pubs = _make_governance_keys(3, 2)
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk, pk = generate_keypair()
    pub = encode_public_key(pk)
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": pub,
        "activation_height": 1,  # must be > block height (1)
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(privs, body)
    tx = {"type": "governance", "body": body}
    block1 = ledger.mine_block_v2([tx])
    assert not ledger.add_block_v2(block1)
