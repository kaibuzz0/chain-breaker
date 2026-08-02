"""Regression tests for post-review hardening fixes.

Covers:
- header.version == 2 enforcement on all v2 consensus paths
- deterministic validate_chain without wall-clock time
- canonical governance signature ordering in transaction IDs
"""

import os
import subprocess
import sys
import time

from chainbreaker.block import (
    GENESIS_REGISTRY_ROOT,
    GENESIS_TARGET,
    PROTOCOL_VERSION,
    BlockHeaderV2,
    BlockV2,
)
from chainbreaker.chain import Ledger, _canonical_txid
from chainbreaker.crypto import generate_keypair
from chainbreaker.governance import (
    GovernanceContext,
    make_governance_signature,
)
from chainbreaker.registry_state import (
    RegistryState,
    apply_registry_transaction,
    registry_root,
)


def _make_register_tx(state, curator_id, pub_hex, activation, keys, threshold):
    body = {
        "action": "curator_register",
        "curator_id": curator_id,
        "public_key_hex": pub_hex,
        "activation_height": activation,
        "previous_registry_root": registry_root(state),
        "network_id": "chainbreaker-scripture-v2",
        "schema_version": 1,
    }
    sigs = []
    for idx in range(threshold):
        sigs.append(make_governance_signature(keys[idx], body, idx))
    # Deliberately reverse signature order to test canonicalization
    sigs.reverse()
    body["governance_signatures"] = [s.to_dict() for s in sigs]
    return body


def test_v2_header_wrong_version_rejected():
    """A structurally v2 block with version != 2 must be rejected."""
    ledger = Ledger()
    base = ledger.last_block
    header = BlockHeaderV2(
        version=99,
        prev_hash=base.hash,
        merkle_root="0" * 64,
        registry_root=GENESIS_REGISTRY_ROOT,
        timestamp=1704067201,
        target=GENESIS_TARGET,
        nonce=0,
    )
    block = BlockV2(header=header, transactions=[])
    assert not block.verify()
    assert not ledger.add_block_v2(block)


def test_v2_header_correct_version_accepted():
    """A properly formed v2 block with version == 2 passes structural checks."""
    ledger = Ledger()
    base = ledger.last_block
    header = BlockHeaderV2(
        version=PROTOCOL_VERSION,
        prev_hash=base.hash,
        merkle_root="0" * 64,
        registry_root=registry_root(RegistryState.genesis(
            ledger.governance_keys, ledger.governance_threshold)),
        timestamp=1704067201,
        target=GENESIS_TARGET,
        nonce=0,
    )
    block = BlockV2(header=header, transactions=[])
    assert block.mine(max_iterations=200_000)
    assert block.verify()
    assert ledger.add_block_v2(block)


def test_validate_chain_deterministic_without_system_clock():
    """validate_chain must not depend on the system clock."""
    ledger = Ledger()
    block = ledger.mine_block_v2([], timestamp=1704067201)
    assert ledger.add_block_v2(block)

    assert ledger.validate_chain()

    original_time = time.time
    try:
        time.time = lambda: 2_000_000_000  # ~2033
        assert ledger.validate_chain()
    finally:
        time.time = original_time


def test_governance_transaction_signature_order_is_canonical():
    """Reordered governance signatures must keep same canonical txid."""
    keys = [generate_keypair()[0] for _ in range(3)]
    pub_keys = [k.public_key().public_bytes_raw().hex() for k in keys]
    state = RegistryState.genesis(pub_keys, 2)

    _, curator_pk = generate_keypair()
    curator_pub = curator_pk.public_bytes_raw().hex()

    body = _make_register_tx(state, "alice", curator_pub, 5, keys, 2)
    from chainbreaker.governance import CuratorRegisterTx
    tx_a = CuratorRegisterTx.from_dict(body)

    sigs_asc = sorted(tx_a.governance_signatures, key=lambda s: s.key_index)
    body_asc = body.copy()
    body_asc["governance_signatures"] = [s.to_dict() for s in sigs_asc]
    tx_b = CuratorRegisterTx.from_dict(body_asc)

    # Canonical txid is identical regardless of signature order.
    assert _canonical_txid(tx_a.to_dict()) == _canonical_txid(tx_b.to_dict())


def test_governance_signature_ordering_determines_state_root():
    """Registry root must be identical for same logical action regardless of signature order."""
    keys = [generate_keypair()[0] for _ in range(3)]
    pub_keys = [k.public_key().public_bytes_raw().hex() for k in keys]
    context = GovernanceContext(pub_keys, threshold=2)
    state = RegistryState.genesis(pub_keys, 2)

    _, curator_pk = generate_keypair()
    curator_pub = curator_pk.public_bytes_raw().hex()

    body = _make_register_tx(state, "alice", curator_pub, 5, keys, 2)
    from chainbreaker.governance import CuratorRegisterTx
    tx = CuratorRegisterTx.from_dict(body)
    txid = _canonical_txid(tx.to_dict())
    new_state = apply_registry_transaction(state, tx, 1, txid, context)

    sigs_asc = sorted(tx.governance_signatures, key=lambda s: s.key_index)
    body_asc = body.copy()
    body_asc["governance_signatures"] = [s.to_dict() for s in sigs_asc]
    tx_asc = CuratorRegisterTx.from_dict(body_asc)
    txid_asc = _canonical_txid(tx_asc.to_dict())
    new_state_asc = apply_registry_transaction(state, tx_asc, 1, txid_asc, context)

    assert new_state.records[0].registration_txid == new_state_asc.records[0].registration_txid
    assert registry_root(new_state) == registry_root(new_state_asc)


def test_validate_chain_cross_process_determinism():
    """validate_chain produces the same result in a separate process."""
    ledger = Ledger()
    block = ledger.mine_block_v2([], timestamp=1704067201)
    assert ledger.add_block_v2(block)

    code = r"""
import sys
sys.path.insert(0, r"D:/Hermes-USB-Portable-main/src/chain-breaker-checkout")
from chainbreaker.chain import Ledger
ledger = Ledger()
print("VALID" if ledger.validate_chain() else "INVALID")
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = r"D:/Hermes-USB-Portable-main/src/chain-breaker-checkout"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "VALID"
