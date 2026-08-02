"""Phase 5C: registry state machine adversarial tests.

Try to make two honest nodes derive different registry states from the same
history, or make one node accept an invalid state transition.
"""


import pytest

from chainbreaker.chain import Ledger
from chainbreaker.crypto import HashEngine, encode_public_key, generate_keypair, sign
from chainbreaker.governance import (
    NETWORK_ID,
    CuratorRegisterTx,
    GovernanceContext,
    GovernanceError,
    GovernanceSignature,
)
from chainbreaker.registry_state import apply_registry_transaction, registry_root


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
    # Curator signatures are computed over the witness-stripped body, matching
    # the verification path in _verify_curator_signature.
    stripped = {k: v for k, v in body.items() if k not in {"governance_signatures", "curator_signature"}}
    message = HashEngine.hash_object({
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(stripped),
    })
    return sign(curator_sk, message)


def test_register_order_does_not_change_active_curators_for_independent_ids():
    """Independent registrations in either order produce the same active curator set.

    Because each transaction's txid includes its chained previous_registry_root,
    the exact registry root differs by transaction order.  Consensus is that both
    blocks are accepted and the same curator IDs become active.
    """
    privs, pubs = _make_governance_keys()
    sk_a, pk_a = generate_keypair()
    sk_b, pk_b = generate_keypair()
    pub_a = encode_public_key(pk_a)
    pub_b = encode_public_key(pk_b)
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    ctx = GovernanceContext(pubs, 2)
    root0 = registry_root(ledger.registry_state_at(0))

    def make_register_body(curator_id: str, public_key_hex: str, previous_root: str) -> dict:
        body = {
            "action": "curator_register",
            "curator_id": curator_id,
            "public_key_hex": public_key_hex,
            "activation_height": 2,
            "previous_registry_root": previous_root,
            "network_id": NETWORK_ID,
            "schema_version": 1,
        }
        body["governance_signatures"] = _sign_body(privs, body)
        return body

    body_a = make_register_body("alice", pub_a, root0)
    reg_a = CuratorRegisterTx.from_dict(body_a)
    root_after_a = registry_root(apply_registry_transaction(ledger.registry_state_at(0), reg_a, 1, HashEngine.hash_object_hex(body_a), ctx))

    body_b = make_register_body("bob", pub_b, root_after_a)

    ledger1 = Ledger(governance_keys=pubs, governance_threshold=2)
    block1 = ledger1.mine_block_v2([{"type": "governance", "body": body_a}, {"type": "governance", "body": body_b}])
    assert ledger1.add_block_v2(block1)

    body_b2 = make_register_body("bob", pub_b, root0)
    reg_b2 = CuratorRegisterTx.from_dict(body_b2)
    root_after_b2 = registry_root(apply_registry_transaction(ledger.registry_state_at(0), reg_b2, 1, HashEngine.hash_object_hex(body_b2), ctx))
    body_a2 = make_register_body("alice", pub_a, root_after_b2)

    ledger2 = Ledger(governance_keys=pubs, governance_threshold=2)
    block2 = ledger2.mine_block_v2([{"type": "governance", "body": body_b2}, {"type": "governance", "body": body_a2}])
    assert ledger2.add_block_v2(block2)

    ids1 = {r.curator_id for r in ledger1.registry_state_at(1).records}
    ids2 = {r.curator_id for r in ledger2.registry_state_at(1).records}
    assert ids1 == ids2 == {"alice", "bob"}


def test_transaction_order_affects_valid_state_transitions():
    """Order must be deterministic: register before rotate works, rotate before register fails."""
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    ctx = GovernanceContext(pubs, 2)
    sk, pk = generate_keypair()
    pub = encode_public_key(pk)
    new_sk, new_pk = generate_keypair()
    new_pub = encode_public_key(new_pk)
    root0 = registry_root(ledger.registry_state_at(0))

    register_body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": pub,
        "activation_height": 2,
        "previous_registry_root": root0,
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    register_body["governance_signatures"] = _sign_body(privs, register_body)

    # Compute state after register to sign rotate correctly
    reg_tx = CuratorRegisterTx.from_dict(register_body)
    state_after_reg = apply_registry_transaction(ledger.registry_state_at(0), reg_tx, 1, HashEngine.hash_object_hex(register_body), ctx)
    root_after_reg = registry_root(state_after_reg)

    rotate_body = {
        "action": "curator_rotate",
        "curator_id": "alice",
        "public_key_hex": pub,
        "new_public_key_hex": new_pub,
        "activation_height": 3,
        "previous_registry_root": root_after_reg,
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    rotate_body["governance_signatures"] = _sign_body(privs, rotate_body)
    rotate_body["curator_signature"] = _curator_sig(sk, rotate_body)

    # register then rotate is valid
    ledger_a = Ledger(governance_keys=pubs, governance_threshold=2)
    block_a = ledger_a.mine_block_v2([
        {"type": "governance", "body": register_body},
        {"type": "governance", "body": rotate_body},
    ])
    assert ledger_a.add_block_v2(block_a)

    # rotate then register is invalid: rotate requires an existing active record
    ledger_b = Ledger(governance_keys=pubs, governance_threshold=2)
    block_b = ledger_b.mine_block_v2([
        {"type": "governance", "body": rotate_body},
        {"type": "governance", "body": register_body},
    ])
    assert not ledger_b.add_block_v2(block_b)


def test_replay_same_register_in_later_block_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk, pk = generate_keypair()
    pub = encode_public_key(pk)
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
    assert ledger.add_block_v2(ledger.mine_block_v2([tx]))

    block2 = ledger.mine_block_v2([tx])
    assert not ledger.add_block_v2(block2)


def test_replay_with_modified_registry_root_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk, pk = generate_keypair()
    pub = encode_public_key(pk)
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
    assert ledger.add_block_v2(ledger.mine_block_v2([tx]))

    replay = dict(body)
    replay["previous_registry_root"] = "00" * 32
    replay["governance_signatures"] = _sign_body(privs, replay)
    block2 = ledger.mine_block_v2([{"type": "governance", "body": replay}])
    assert not ledger.add_block_v2(block2)


def test_activation_height_equal_block_height_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk, pk = generate_keypair()
    pub = encode_public_key(pk)
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": pub,
        "activation_height": 1,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(privs, body)
    block1 = ledger.mine_block_v2([{"type": "governance", "body": body}])
    assert not ledger.add_block_v2(block1)


def test_activation_height_block_plus_one_accepted():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk, pk = generate_keypair()
    pub = encode_public_key(pk)
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
    block1 = ledger.mine_block_v2([{"type": "governance", "body": body}])
    assert ledger.add_block_v2(block1)
    state = ledger.registry_state_at(1)
    assert state.is_active("alice", 2)
    assert not state.is_active("alice", 1)


def test_activation_height_far_future():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk, pk = generate_keypair()
    pub = encode_public_key(pk)
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": pub,
        "activation_height": 1_000_000,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(privs, body)
    block1 = ledger.mine_block_v2([{"type": "governance", "body": body}])
    assert ledger.add_block_v2(block1)


def test_negative_activation_height_rejected():
    from chainbreaker.governance import _require_height
    with pytest.raises(GovernanceError):
        _require_height(-1, "activation_height")


def test_cache_corruption_detected_by_validate_chain():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk, pk = generate_keypair()
    pub = encode_public_key(pk)
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
    assert ledger.add_block_v2(ledger.mine_block_v2([{"type": "governance", "body": body}]))

    # Corrupt the cached registry state
    ledger.registry_states[1] = ledger.registry_states[0]
    assert not ledger.validate_chain()


def test_determinism_across_independent_ledgers():
    privs, pubs = _make_governance_keys()

    sk_shared, pk_shared = generate_keypair()
    pub_shared = encode_public_key(pk_shared)

    def build():
        ledger = Ledger(governance_keys=pubs, governance_threshold=2)
        body = {
            "action": "curator_register",
            "curator_id": "alice",
            "public_key_hex": pub_shared,
            "activation_height": 2,
            "previous_registry_root": registry_root(ledger.registry_state_at(0)),
            "network_id": NETWORK_ID,
            "schema_version": 1,
        }
        body["governance_signatures"] = _sign_body(privs, body)
        ledger.add_block_v2(ledger.mine_block_v2([{"type": "governance", "body": body}]))
        return ledger

    l1 = build()
    l2 = build()
    assert registry_root(l1.registry_state_at(1)) == registry_root(l2.registry_state_at(1))



def test_failed_transaction_leaves_state_unchanged():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    root_before = registry_root(ledger.registry_state_at(0))

    # Valid register
    sk, pk = generate_keypair()
    pub = encode_public_key(pk)
    good_body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": pub,
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    good_body["governance_signatures"] = _sign_body(privs, good_body)
    # Invalid duplicate
    dup_body = dict(good_body)
    dup_body["governance_signatures"] = _sign_body(privs, dup_body)

    block1 = ledger.mine_block_v2([
        {"type": "governance", "body": good_body},
        {"type": "governance", "body": dup_body},
    ])
    assert not ledger.add_block_v2(block1)
    assert registry_root(ledger.registry_state_at(0)) == root_before
    assert ledger.height() == 0
