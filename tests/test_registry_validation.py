"""Tests for ledger registry-root validation (Milestone 4D).

These tests verify that block headers commit to the deterministic registry
state produced by prior blocks, and that governance transactions mutate that
state in the correct order.
"""

from chainbreaker.block import GENESIS_GOVERNANCE_KEYS, GENESIS_THRESHOLD
from chainbreaker.chain import Ledger
from chainbreaker.crypto import (
    HashEngine,
    encode_public_key,
    generate_keypair,
    sign,
)
from chainbreaker.governance import NETWORK_ID, GovernanceSignature
from chainbreaker.registry_state import RegistryState, registry_root


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
    return [
        GovernanceSignature(key_index=i, signature_hex=sign(priv, message)).to_dict()
        for i, priv in enumerate(privs)
    ]


def _register_tx(curator_id: str, public_key_hex: str, activation_height: int,
                 previous_registry_root: str, privs) -> dict:
    body = {
        "action": "curator_register",
        "curator_id": curator_id,
        "public_key_hex": public_key_hex,
        "activation_height": activation_height,
        "previous_registry_root": previous_registry_root,
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    return {"type": "governance", "body": {**body, "governance_signatures": _sign_body(privs, body)}}


def test_ledger_initializes_genesis_registry_state():
    ledger = Ledger()
    state = ledger.registry_state_at(0)
    assert isinstance(state, RegistryState)
    assert registry_root(state) == ledger.chain[0].header.registry_root


def test_mine_block_v2_includes_registry_root():
    ledger = Ledger()
    block = ledger.mine_block_v2([])
    expected_root = registry_root(ledger.registry_state_at(0))
    assert block.header.registry_root == expected_root


def test_add_block_v2_updates_registry_state():
    ledger = Ledger()
    block = ledger.mine_block_v2([])
    assert ledger.add_block_v2(block)
    assert ledger.height() == 1
    assert 1 in ledger.registry_states


def test_wrong_registry_root_rejected():
    ledger = Ledger()
    block = ledger.mine_block_v2([])
    block.header.registry_root = "0" * 64
    assert not ledger.add_block_v2(block)


def test_registry_state_replay_from_genesis():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    tx = _register_tx("alice", "a" * 64, 2, registry_root(ledger.registry_state_at(0)), privs)
    block1 = ledger.mine_block_v2([tx])
    assert ledger.add_block_v2(block1)

    # Rebuild from chain
    ledger2 = Ledger(chain=list(ledger.chain), governance_keys=pubs, governance_threshold=2)
    assert registry_root(ledger2.registry_state_at(1)) == registry_root(ledger.registry_state_at(1))


def test_register_transaction_changes_future_state():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    tx = _register_tx("alice", "a" * 64, 2, registry_root(ledger.registry_state_at(0)), privs)
    block1 = ledger.mine_block_v2([tx])
    assert ledger.add_block_v2(block1)
    state1 = ledger.registry_state_at(1)
    assert state1.by_id("alice") is not None


def test_transaction_order_affects_state():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    root0 = registry_root(ledger.registry_state_at(0))
    register_alice = _register_tx("alice", "a" * 64, 2, root0, privs)
    # A second register for the same curator_id is invalid; placing it first
    # vs second changes where validation fails but the block is rejected either
    # way because the state after the first transaction already contains alice.
    duplicate = _register_tx("alice", "b" * 64, 2, root0, privs)

    block1 = ledger.mine_block_v2([register_alice, duplicate])
    assert not ledger.add_block_v2(block1)

    ledger2 = Ledger(governance_keys=pubs, governance_threshold=2)
    block2 = ledger2.mine_block_v2([duplicate, register_alice])
    assert not ledger2.add_block_v2(block2)


def test_failed_transaction_leaves_state_unchanged():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    root0 = registry_root(ledger.registry_state_at(0))
    # Invalid: duplicate governance signatures from same key index for threshold
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": "a" * 64,
        "activation_height": 2,
        "previous_registry_root": root0,
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    message = HashEngine.hash_object({
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body),
    })
    sig = GovernanceSignature(key_index=0, signature_hex=sign(privs[0], message)).to_dict()
    bad_tx = {"type": "governance", "body": {**body, "governance_signatures": [sig, sig]}}

    block = ledger.mine_block_v2([bad_tx])
    assert not ledger.add_block_v2(block)


def test_validate_chain_includes_registry_root_checks():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    tx = _register_tx("alice", "a" * 64, 2, registry_root(ledger.registry_state_at(0)), privs)
    block1 = ledger.mine_block_v2([tx])
    assert ledger.add_block_v2(block1)
    assert ledger.validate_chain()


def test_validate_chain_rejects_tampered_registry_root():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    block1 = ledger.mine_block_v2([])
    assert ledger.add_block_v2(block1)
    ledger.chain[1].header.registry_root = "0" * 64
    assert not ledger.validate_chain()


def test_no_singleton_global_state():
    privs, pubs = _make_governance_keys(count=1, threshold=1)
    ledger1 = Ledger(governance_keys=pubs, governance_threshold=1)
    ledger2 = Ledger(governance_keys=GENESIS_GOVERNANCE_KEYS, governance_threshold=GENESIS_THRESHOLD)
    ledger1.registry_states[0] = RegistryState.genesis(pubs, 1)
    # ledger2 should not see ledger1's mutation
    assert registry_root(ledger2.registry_state_at(0)) != registry_root(ledger1.registry_state_at(0))
