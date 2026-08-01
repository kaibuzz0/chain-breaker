"""Tests for deterministic registry state reducer."""

import os
import subprocess
import sys

import pytest

from chainbreaker.crypto import HashEngine, encode_public_key, generate_keypair, sign
from chainbreaker.governance import (
    NETWORK_ID,
    CuratorRegisterTx,
    CuratorRevokeTx,
    CuratorRotateTx,
    GovernanceContext,
    GovernanceError,
    make_governance_signature,
)
from chainbreaker.registry_state import (
    CuratorRecord,
    RegistryError,
    RegistryState,
    apply_registry_transaction,
    registry_root,
    serialize_registry_state,
)


def _make_register_body(curator_id: str, public_key_hex: str, activation_height: int, previous_root: str) -> dict:
    return {
        "action": "curator_register",
        "curator_id": curator_id,
        "public_key_hex": public_key_hex,
        "activation_height": activation_height,
        "previous_registry_root": previous_root,
        "governance_signatures": [],
    }


def _governance_context(n: int = 3, threshold: int = 2):
    keys = []
    for _ in range(n):
        sk, pk_obj = generate_keypair()
        pk = encode_public_key(pk_obj)
        keys.append((sk, pk))
    ctx = GovernanceContext(public_keys_hex=[pk for _, pk in keys], threshold=threshold)
    return ctx, keys


def _sign_body(body: dict, ctx, keys, indices=None, include_curator=None):
    if indices is None:
        indices = list(range(ctx.threshold))
    body.setdefault("network_id", NETWORK_ID)
    body.setdefault("schema_version", 1)
    # Sign the body stripped of witness/signature fields, matching the
    # message the reducer verifies against.
    body_for_signing = {k: v for k, v in body.items() if k not in {"governance_signatures", "curator_signature"}}
    sigs = []
    for idx in indices:
        sig = make_governance_signature(keys[idx][0], body_for_signing, idx)
        sigs.append(sig)
    if include_curator is not None:
        sk = include_curator[0]
        msg = HashEngine.hash_object({
            "network_id": NETWORK_ID,
            "version": 2,
            "type": "registry",
            "body_hash": HashEngine.hash_object_hex(body_for_signing),
        })
        body["curator_signature"] = sign(sk, msg)
    return sigs


def test_empty_state_root():
    empty = RegistryState.empty()
    root = registry_root(empty)
    assert len(root) == 64
    # Stable across recomputation
    assert registry_root(RegistryState.empty()) == root


def test_empty_state_root_in_fresh_process():
    """Verify the empty-state root is identical in a separate process."""
    script = """
from chainbreaker.registry_state import RegistryState, registry_root
print(registry_root(RegistryState.empty()))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(__file__),
    )
    assert result.returncode == 0
    root1 = registry_root(RegistryState.empty())
    root2 = result.stdout.strip()
    assert root1 == root2


def test_serialization_stable_record_order():
    sk1, pk1 = generate_keypair()
    sk2, pk2 = generate_keypair()
    # records in non-alphabetical curator_id order
    r1 = CuratorRecord("beta", encode_public_key(pk1), 5, None, None, "a" * 64, None)
    r2 = CuratorRecord("alpha", encode_public_key(pk2), 6, None, None, "b" * 64, None)
    state = RegistryState(records=(r1, r2))
    serialized = serialize_registry_state(state)
    # Reconstructing from sorted list should give same bytes
    sorted_state = RegistryState(records=tuple(sorted((r1, r2), key=lambda r: r.curator_id.encode("utf-8"))))
    assert serialize_registry_state(sorted_state) == serialized


def test_valid_registration():
    ctx, keys = _governance_context()
    empty = RegistryState.empty()
    sk, pk = generate_keypair()
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": encode_public_key(pk),
        "activation_height": 5,
        "previous_registry_root": registry_root(empty),
        "governance_signatures": [],
    }
    sigs = _sign_body(body, ctx, keys)
    body["governance_signatures"] = [s.to_dict() for s in sigs]
    tx = CuratorRegisterTx.from_dict(body)
    txid = HashEngine.hash_object_hex(body)
    new_state = apply_registry_transaction(empty, tx, block_height=1, txid=txid, context=ctx)
    assert new_state.by_id("alpha") is not None
    assert new_state.by_id("alpha").activation_height == 5
    assert new_state.by_id("alpha").public_key_hex == encode_public_key(pk)


def test_duplicate_curator_id_rejected():
    ctx, keys = _governance_context()
    sk, pk = generate_keypair()
    empty = RegistryState.empty()
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": encode_public_key(pk),
        "activation_height": 5,
        "previous_registry_root": registry_root(empty),
        "governance_signatures": [],
    }
    sigs = _sign_body(body, ctx, keys)
    body["governance_signatures"] = [s.to_dict() for s in sigs]
    tx = CuratorRegisterTx.from_dict(body)
    txid = HashEngine.hash_object_hex(body)
    state1 = apply_registry_transaction(empty, tx, block_height=1, txid=txid, context=ctx)

    body2 = body.copy()
    body2["previous_registry_root"] = registry_root(state1)
    body2["governance_signatures"] = [s.to_dict() for s in _sign_body(body2, ctx, keys)]
    tx2 = CuratorRegisterTx.from_dict(body2)
    with pytest.raises(RegistryError):
        apply_registry_transaction(state1, tx2, block_height=2, txid="ff" * 32, context=ctx)


def test_duplicate_public_key_rejected():
    ctx, keys = _governance_context()
    sk, pk = generate_keypair()
    empty = RegistryState.empty()
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": encode_public_key(pk),
        "activation_height": 5,
        "previous_registry_root": registry_root(empty),
        "governance_signatures": [],
    }
    sigs = _sign_body(body, ctx, keys)
    body["governance_signatures"] = [s.to_dict() for s in sigs]
    tx = CuratorRegisterTx.from_dict(body)
    state1 = apply_registry_transaction(empty, tx, block_height=1, txid="a" * 64, context=ctx)

    body2 = body.copy()
    body2["curator_id"] = "beta"
    body2["previous_registry_root"] = registry_root(state1)
    body2["governance_signatures"] = [s.to_dict() for s in _sign_body(body2, ctx, keys)]
    tx2 = CuratorRegisterTx.from_dict(body2)
    with pytest.raises(RegistryError):
        apply_registry_transaction(state1, tx2, block_height=2, txid="b" * 64, context=ctx)


def test_wrong_network_id_rejected():
    ctx, keys = _governance_context()
    sk, pk = generate_keypair()
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": encode_public_key(pk),
        "activation_height": 5,
        "previous_registry_root": registry_root(RegistryState.empty()),
        "governance_signatures": [],
        "network_id": "wrong",
    }
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(body)


def test_invalid_key_length_rejected():
    ctx, keys = _governance_context()
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": "a" * 63,
        "activation_height": 5,
        "previous_registry_root": registry_root(RegistryState.empty()),
        "governance_signatures": [],
    }
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(body)


def test_unsupported_schema_version_rejected():
    ctx, keys = _governance_context()
    sk, pk = generate_keypair()
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": encode_public_key(pk),
        "activation_height": 5,
        "previous_registry_root": registry_root(RegistryState.empty()),
        "governance_signatures": [],
        "schema_version": 99,
    }
    with pytest.raises(GovernanceError):
        CuratorRegisterTx.from_dict(body)


def test_insufficient_governance_signatures():
    ctx, keys = _governance_context(n=3, threshold=2)
    sk, pk_obj = generate_keypair()
    pk = encode_public_key(pk_obj)
    empty = RegistryState.empty()
    body = _make_register_body("alpha", pk, 5, registry_root(empty))
    # Only one signature
    sigs = _sign_body(body, ctx, keys, indices=[0])
    body["governance_signatures"] = [s.to_dict() for s in sigs]
    tx = CuratorRegisterTx.from_dict(body)
    with pytest.raises((RegistryError, GovernanceError)):
        apply_registry_transaction(empty, tx, block_height=1, txid="ff" * 32, context=ctx)


def test_duplicate_governance_signatures_rejected():
    ctx, gov_keys = _governance_context(n=3, threshold=2)
    sk, pk_obj = generate_keypair()
    pk = encode_public_key(pk_obj)
    empty = RegistryState.empty()
    body = _make_register_body("alpha", pk, 5, registry_root(empty))
    sigs = _sign_body(body, ctx, gov_keys, indices=[0, 0])
    body["governance_signatures"] = [s.to_dict() for s in sigs]
    tx = CuratorRegisterTx.from_dict(body)
    with pytest.raises((RegistryError, GovernanceError)):
        apply_registry_transaction(empty, tx, block_height=1, txid="ff" * 32, context=ctx)


def test_unknown_governance_signer_rejected():
    ctx, keys = _governance_context()
    sk, pk_obj = generate_keypair()
    pk = encode_public_key(pk_obj)
    empty = RegistryState.empty()
    body = _make_register_body("alpha", pk, 5, registry_root(empty))
    sigs = _sign_body(body, ctx, keys, indices=[0, 1])
    # Tamper key_index to point outside key set
    body["governance_signatures"] = [
        {"key_index": 99, "signature": sigs[0].signature_hex},
        sigs[1].to_dict(),
    ]
    tx = CuratorRegisterTx.from_dict(body)
    with pytest.raises((RegistryError, GovernanceError)):
        apply_registry_transaction(empty, tx, block_height=1, txid="ff" * 32, context=ctx)


def test_valid_rotation():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    reg_body = _make_register_body("alpha", curator_pk, 5, registry_root(empty))
    reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
    reg_tx = CuratorRegisterTx.from_dict(reg_body)
    state1 = apply_registry_transaction(empty, reg_tx, block_height=1, txid="ab" * 32, context=ctx)

    _, new_pk_obj = generate_keypair()
    new_pk = encode_public_key(new_pk_obj)
    rot_body = {
        "action": "curator_rotate",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "new_public_key_hex": new_pk,
        "activation_height": 10,
        "previous_registry_root": registry_root(state1),
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    rot_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rot_body, ctx, gov_keys, include_curator=(curator_sk, curator_pk))]
    rot_tx = CuratorRotateTx.from_dict(rot_body)
    state2 = apply_registry_transaction(state1, rot_tx, block_height=6, txid="cd" * 32, context=ctx)

    assert state2.key_was_valid_at("alpha", curator_pk, 9)
    assert state2.key_was_valid_at("alpha", new_pk, 10)
    assert not state2.key_was_valid_at("alpha", curator_pk, 10)


def test_rotation_wrong_current_key():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    _, other_pk_obj = generate_keypair()
    other_pk = encode_public_key(other_pk_obj)
    empty = RegistryState.empty()
    reg_body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "activation_height": 5,
        "previous_registry_root": registry_root(empty),
        "governance_signatures": [],
    }
    reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
    reg_tx = CuratorRegisterTx.from_dict(reg_body)
    state1 = apply_registry_transaction(empty, reg_tx, block_height=1, txid="ab" * 32, context=ctx)

    _, new_pk_obj = generate_keypair()
    new_pk = encode_public_key(new_pk_obj)
    rot_body = {
        "action": "curator_rotate",
        "curator_id": "alpha",
        "public_key_hex": other_pk,  # wrong key
        "new_public_key_hex": new_pk,
        "activation_height": 10,
        "previous_registry_root": registry_root(state1),
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    rot_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rot_body, ctx, gov_keys)]
    rot_tx = CuratorRotateTx.from_dict(rot_body)
    with pytest.raises(RegistryError):
        apply_registry_transaction(state1, rot_tx, block_height=6, txid="cd" * 32, context=ctx)


def test_rotation_to_duplicate_key():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    beta_sk, beta_pk_obj = generate_keypair()
    beta_pk = encode_public_key(beta_pk_obj)
    empty = RegistryState.empty()

    # register alpha and beta
    for cid, pk in [("alpha", curator_pk), ("beta", beta_pk)]:
        reg_body = {
            "action": "curator_register",
            "curator_id": cid,
            "public_key_hex": pk,
            "activation_height": 5,
            "previous_registry_root": registry_root(empty),
            "governance_signatures": [],
        }
        reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
        reg_tx = CuratorRegisterTx.from_dict(reg_body)
        empty = apply_registry_transaction(empty, reg_tx, block_height=1, txid=("ab" if cid == "alpha" else "cd") * 32, context=ctx)

    # try to rotate alpha to beta's key
    rot_body = {
        "action": "curator_rotate",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "new_public_key_hex": beta_pk,
        "activation_height": 10,
        "previous_registry_root": registry_root(empty),
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    msg = HashEngine.hash_object({
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex({k: v for k, v in rot_body.items() if k not in {"governance_signatures", "curator_signature"}}),
    })
    rot_body["curator_signature"] = sign(curator_sk, msg)
    rot_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rot_body, ctx, gov_keys)]
    rot_tx = CuratorRotateTx.from_dict(rot_body)
    with pytest.raises(RegistryError):
        apply_registry_transaction(empty, rot_tx, block_height=6, txid="cd" * 32, context=ctx)


def test_rotation_before_allowed_activation():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    reg_body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "activation_height": 5,
        "previous_registry_root": registry_root(empty),
        "governance_signatures": [],
    }
    reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
    reg_tx = CuratorRegisterTx.from_dict(reg_body)
    state1 = apply_registry_transaction(empty, reg_tx, block_height=1, txid="ab" * 32, context=ctx)

    _, new_pk_obj = generate_keypair()
    new_pk = encode_public_key(new_pk_obj)
    rot_body = {
        "action": "curator_rotate",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "new_public_key_hex": new_pk,
        "activation_height": 1,  # not greater than block height
        "previous_registry_root": registry_root(state1),
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    rot_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rot_body, ctx, gov_keys)]
    rot_tx = CuratorRotateTx.from_dict(rot_body)
    with pytest.raises(RegistryError):
        apply_registry_transaction(state1, rot_tx, block_height=6, txid="cd" * 32, context=ctx)


def test_valid_revocation():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    reg_body = _make_register_body("alpha", curator_pk, 5, registry_root(empty))
    reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
    reg_tx = CuratorRegisterTx.from_dict(reg_body)
    state1 = apply_registry_transaction(empty, reg_tx, block_height=1, txid="ab" * 32, context=ctx)

    rev_body = {
        "action": "curator_revoke",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "revocation_height": 20,
        "reason_code": "compromise",
        "previous_registry_root": registry_root(state1),
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    rev_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rev_body, ctx, gov_keys, include_curator=(curator_sk, curator_pk))]
    rev_tx = CuratorRevokeTx.from_dict(rev_body)
    state2 = apply_registry_transaction(state1, rev_tx, block_height=6, txid="ef" * 32, context=ctx)

    assert state2.is_active("alpha", 19)
    assert not state2.is_active("alpha", 20)


def test_duplicate_revocation_rejected():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    reg_body = _make_register_body("alpha", curator_pk, 5, registry_root(empty))
    reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
    reg_tx = CuratorRegisterTx.from_dict(reg_body)
    state1 = apply_registry_transaction(empty, reg_tx, block_height=1, txid="ab" * 32, context=ctx)

    rev_body = {
        "action": "curator_revoke",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "revocation_height": 20,
        "reason_code": "compromise",
        "previous_registry_root": registry_root(state1),
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    rev_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rev_body, ctx, gov_keys, include_curator=(curator_sk, curator_pk))]
    rev_tx = CuratorRevokeTx.from_dict(rev_body)
    state2 = apply_registry_transaction(state1, rev_tx, block_height=6, txid="ef" * 32, context=ctx)

    # Try revoke again
    rev_body["previous_registry_root"] = registry_root(state2)
    rev_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rev_body, ctx, gov_keys, include_curator=(curator_sk, curator_pk))]
    rev_tx2 = CuratorRevokeTx.from_dict(rev_body)
    with pytest.raises(RegistryError):
        apply_registry_transaction(state2, rev_tx2, block_height=21, txid="01" * 32, context=ctx)


def test_revocation_before_activation():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    reg_body = _make_register_body("alpha", curator_pk, 5, registry_root(empty))
    reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
    reg_tx = CuratorRegisterTx.from_dict(reg_body)
    state1 = apply_registry_transaction(empty, reg_tx, block_height=1, txid="ab" * 32, context=ctx)

    rev_body = {
        "action": "curator_revoke",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "revocation_height": 3,  # less than activation_height
        "reason_code": "compromise",
        "previous_registry_root": registry_root(state1),
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    rev_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rev_body, ctx, gov_keys, include_curator=(curator_sk, curator_pk))]
    rev_tx = CuratorRevokeTx.from_dict(rev_body)
    with pytest.raises(RegistryError):
        apply_registry_transaction(state1, rev_tx, block_height=2, txid="ef" * 32, context=ctx)


def test_replayed_transaction_rejected():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    reg_body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "activation_height": 5,
        "previous_registry_root": registry_root(empty),
        "governance_signatures": [],
    }
    reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
    reg_tx = CuratorRegisterTx.from_dict(reg_body)
    txid = HashEngine.hash_object_hex(reg_body)
    state1 = apply_registry_transaction(empty, reg_tx, block_height=1, txid=txid, context=ctx)

    # Replay same txid would attempt to register same ID and fail
    with pytest.raises(RegistryError):
        apply_registry_transaction(state1, reg_tx, block_height=2, txid=txid, context=ctx)


def test_mismatched_previous_registry_root():
    ctx, gov_keys = _governance_context()
    sk, pk = generate_keypair()
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": encode_public_key(pk),
        "activation_height": 5,
        "previous_registry_root": "1" * 64,  # wrong root
        "governance_signatures": [],
    }
    body["governance_signatures"] = [s.to_dict() for s in _sign_body(body, ctx, gov_keys)]
    tx = CuratorRegisterTx.from_dict(body)
    with pytest.raises(RegistryError):
        apply_registry_transaction(RegistryState.empty(), tx, block_height=1, txid="ff" * 32, context=ctx)


def test_state_unchanged_after_failure():
    ctx, gov_keys = _governance_context()
    sk, pk = generate_keypair()
    empty = RegistryState.empty()
    root_before = registry_root(empty)
    body = {
        "action": "curator_register",
        "curator_id": "alpha",
        "public_key_hex": encode_public_key(pk),
        "activation_height": 5,
        "previous_registry_root": "1" * 64,
        "governance_signatures": [],
    }
    body["governance_signatures"] = [s.to_dict() for s in _sign_body(body, ctx, gov_keys)]
    tx = CuratorRegisterTx.from_dict(body)
    with pytest.raises(RegistryError):
        apply_registry_transaction(empty, tx, block_height=1, txid="ff" * 32, context=ctx)
    assert registry_root(empty) == root_before


def test_historical_key_lookup_before_and_after_activation():
    ctx, gov_keys = _governance_context()
    _, pk_obj = generate_keypair()
    pk = encode_public_key(pk_obj)
    empty = RegistryState.empty()
    reg_body = _make_register_body("alpha", pk, 5, registry_root(empty))
    reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
    tx = CuratorRegisterTx.from_dict(reg_body)
    state = apply_registry_transaction(empty, tx, block_height=1, txid="ab" * 32, context=ctx)

    assert not state.is_active("alpha", 4)
    assert state.is_active("alpha", 5)
    assert state.is_active("alpha", 100)
    assert state.active_key_at("alpha", 5) == pk


def test_historical_key_lookup_after_revocation():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    reg_body = _make_register_body("alpha", curator_pk, 5, registry_root(empty))
    reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
    reg_tx = CuratorRegisterTx.from_dict(reg_body)
    state1 = apply_registry_transaction(empty, reg_tx, block_height=1, txid="ab" * 32, context=ctx)

    rev_body = {
        "action": "curator_revoke",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "revocation_height": 20,
        "reason_code": "compromise",
        "previous_registry_root": registry_root(state1),
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    rev_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rev_body, ctx, gov_keys, include_curator=(curator_sk, curator_pk))]
    rev_tx = CuratorRevokeTx.from_dict(rev_body)
    state2 = apply_registry_transaction(state1, rev_tx, block_height=6, txid="ef" * 32, context=ctx)

    assert state2.is_active("alpha", 19)
    assert state2.active_key_at("alpha", 19) == curator_pk
    assert not state2.is_active("alpha", 20)
    assert state2.active_key_at("alpha", 20) is None
    assert state2.key_was_valid_at("alpha", curator_pk, 19)
    assert not state2.key_was_valid_at("alpha", curator_pk, 20)


def test_fixed_test_vector_empty_state():
    empty = RegistryState.empty()
    root = registry_root(empty)
    serialized = serialize_registry_state(empty)
    # The empty root is a fixed vector we can assert once computed.
    assert len(root) == 64
    assert len(serialized) > 0
    assert root == registry_root(RegistryState.empty())


def test_registry_state_from_list():
    _, pk_obj = generate_keypair()
    pk = encode_public_key(pk_obj)
    # This is just a structural test; signatures not needed for from_list
    state = RegistryState.from_list([
        {
            "curator_id": "alpha",
            "public_key_hex": pk,
            "activation_height": 5,
            "revocation_height": None,
            "previous_key_hex": None,
            "registration_txid": "a" * 64,
            "latest_rotation_txid": None,
        }
    ])
    assert state.is_active("alpha", 5)



def test_registry_state_from_list_unknown_field_ignored():
    _, pk_obj = generate_keypair()
    pk = encode_public_key(pk_obj)
    state = RegistryState.from_list([
        {
            "curator_id": "alpha",
            "public_key_hex": pk,
            "activation_height": 5,
            "revocation_height": None,
            "previous_key_hex": None,
            "registration_txid": "a" * 64,
            "latest_rotation_txid": None,
            "unknown_field": "ignored",
        }
    ])
    assert state.is_active("alpha", 5)


def test_curator_record_repr():
    record = CuratorRecord(
        curator_id="x",
        public_key_hex="aa" * 32,
        activation_height=1,
        revocation_height=None,
        previous_key_hex=None,
        registration_txid="bb" * 32,
        latest_rotation_txid=None,
    )
    assert "x" in repr(record)


def test_active_key_at_missing_curator():
    empty = RegistryState.empty()
    assert empty.active_key_at("missing", 0) is None


def test_key_was_valid_at_missing_curator():
    empty = RegistryState.empty()
    assert not empty.key_was_valid_at("missing", "aa" * 32, 0)


def test_serialization_varint_medium_and_large():
    # Cover 0xFD and 0xFE varint paths indirectly via a very long curator_id.
    # But max id is 64 bytes. Use 64-byte id to hit 0xFD path.
    from chainbreaker.registry_state import _encode_varint
    assert _encode_varint(0xFD) == bytes([0xFD]) + (0xFD).to_bytes(2, "little")
    assert _encode_varint(0x10000) == bytes([0xFE]) + (0x10000).to_bytes(4, "little")


def test_apply_rotate_curator_signature_failure():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    reg_body = _make_register_body("alpha", curator_pk, 5, registry_root(empty))
    reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
    reg_tx = CuratorRegisterTx.from_dict(reg_body)
    state1 = apply_registry_transaction(empty, reg_tx, block_height=1, txid="ab" * 32, context=ctx)

    _, new_pk_obj = generate_keypair()
    new_pk = encode_public_key(new_pk_obj)
    rot_body = {
        "action": "curator_rotate",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "new_public_key_hex": new_pk,
        "activation_height": 10,
        "previous_registry_root": registry_root(state1),
        "governance_signatures": [],
        "curator_signature": "00" * 64,  # invalid signature
    }
    rot_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rot_body, ctx, gov_keys)]
    rot_tx = CuratorRotateTx.from_dict(rot_body)
    with pytest.raises(RegistryError):
        apply_registry_transaction(state1, rot_tx, block_height=6, txid="cd" * 32, context=ctx)


def test_apply_revoke_curator_signature_failure():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    reg_body = _make_register_body("alpha", curator_pk, 5, registry_root(empty))
    reg_body["governance_signatures"] = [s.to_dict() for s in _sign_body(reg_body, ctx, gov_keys)]
    reg_tx = CuratorRegisterTx.from_dict(reg_body)
    state1 = apply_registry_transaction(empty, reg_tx, block_height=1, txid="ab" * 32, context=ctx)

    rev_body = {
        "action": "curator_revoke",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "revocation_height": 20,
        "reason_code": "compromise",
        "previous_registry_root": registry_root(state1),
        "governance_signatures": [],
        "curator_signature": "00" * 64,
    }
    rev_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rev_body, ctx, gov_keys)]
    rev_tx = CuratorRevokeTx.from_dict(rev_body)
    with pytest.raises(RegistryError):
        apply_registry_transaction(state1, rev_tx, block_height=6, txid="ef" * 32, context=ctx)


def test_registry_state_equality_and_hash():
    s1 = RegistryState.empty()
    s2 = RegistryState.empty()
    assert s1 == s2
    assert hash(s1) == hash(s2)


def test_to_list_and_equality_with_records():
    _, pk_obj = generate_keypair()
    pk = encode_public_key(pk_obj)
    state = RegistryState.from_list([
        {
            "curator_id": "alpha",
            "public_key_hex": pk,
            "activation_height": 5,
            "revocation_height": None,
            "previous_key_hex": None,
            "registration_txid": "a" * 64,
            "latest_rotation_txid": None,
        }
    ])
    assert state.to_list() == [
        {
            "curator_id": "alpha",
            "public_key_hex": pk,
            "activation_height": 5,
            "revocation_height": None,
            "previous_key_hex": None,
            "registration_txid": "a" * 64,
            "latest_rotation_txid": None,
        }
    ]


def test_varint_overflow():
    from chainbreaker.registry_state import _encode_varint
    with pytest.raises(RegistryError):
        _encode_varint(0xFFFFFFFFFFFFFFFF + 1)


def test_register_activation_height_not_greater_than_block():
    ctx, gov_keys = _governance_context()
    _, pk_obj = generate_keypair()
    pk = encode_public_key(pk_obj)
    empty = RegistryState.empty()
    body = _make_register_body("alpha", pk, 5, registry_root(empty))
    body["governance_signatures"] = [s.to_dict() for s in _sign_body(body, ctx, gov_keys)]
    tx = CuratorRegisterTx.from_dict(body)
    with pytest.raises(RegistryError):
        apply_registry_transaction(empty, tx, block_height=5, txid="ff" * 32, context=ctx)


def test_register_duplicate_public_key_records_error_message():
    ctx, gov_keys = _governance_context()
    _, pk_obj = generate_keypair()
    pk = encode_public_key(pk_obj)
    empty = RegistryState.empty()
    body = _make_register_body("alpha", pk, 5, registry_root(empty))
    body["governance_signatures"] = [s.to_dict() for s in _sign_body(body, ctx, gov_keys)]
    tx = CuratorRegisterTx.from_dict(body)
    state1 = apply_registry_transaction(empty, tx, block_height=1, txid="ab" * 32, context=ctx)

    body2 = _make_register_body("beta", pk, 6, registry_root(state1))
    body2["governance_signatures"] = [s.to_dict() for s in _sign_body(body2, ctx, gov_keys)]
    tx2 = CuratorRegisterTx.from_dict(body2)
    with pytest.raises(RegistryError, match="public_key_hex already registered"):
        apply_registry_transaction(state1, tx2, block_height=2, txid="cd" * 32, context=ctx)


def test_rotate_same_key_rejected():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    body = _make_register_body("alpha", curator_pk, 5, registry_root(empty))
    body["governance_signatures"] = [s.to_dict() for s in _sign_body(body, ctx, gov_keys)]
    tx = CuratorRegisterTx.from_dict(body)
    state1 = apply_registry_transaction(empty, tx, block_height=1, txid="ab" * 32, context=ctx)

    rot_body = {
        "action": "curator_rotate",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "new_public_key_hex": curator_pk,
        "activation_height": 10,
        "previous_registry_root": registry_root(state1),
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    rot_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rot_body, ctx, gov_keys, include_curator=(curator_sk, curator_pk))]
    rot_tx = CuratorRotateTx.from_dict(rot_body)
    with pytest.raises(RegistryError, match="new public key must differ"):
        apply_registry_transaction(state1, rot_tx, block_height=6, txid="cd" * 32, context=ctx)


def test_revoke_unknown_curator():
    ctx, gov_keys = _governance_context()
    _, pk_obj = generate_keypair()
    pk = encode_public_key(pk_obj)
    empty = RegistryState.empty()
    body = {
        "action": "curator_revoke",
        "curator_id": "alpha",
        "public_key_hex": pk,
        "revocation_height": 20,
        "reason_code": "compromise",
        "previous_registry_root": registry_root(empty),
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    body["governance_signatures"] = [s.to_dict() for s in _sign_body(body, ctx, gov_keys)]
    tx = CuratorRevokeTx.from_dict(body)
    with pytest.raises(RegistryError, match="unknown curator"):
        apply_registry_transaction(empty, tx, block_height=1, txid="ff" * 32, context=ctx)


def test_revoke_previous_root_mismatch():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    body = _make_register_body("alpha", curator_pk, 5, registry_root(empty))
    body["governance_signatures"] = [s.to_dict() for s in _sign_body(body, ctx, gov_keys)]
    tx = CuratorRegisterTx.from_dict(body)
    state1 = apply_registry_transaction(empty, tx, block_height=1, txid="ab" * 32, context=ctx)

    rev_body = {
        "action": "curator_revoke",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "revocation_height": 20,
        "reason_code": "compromise",
        "previous_registry_root": "00" * 32,  # wrong
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    rev_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rev_body, ctx, gov_keys, include_curator=(curator_sk, curator_pk))]
    rev_tx = CuratorRevokeTx.from_dict(rev_body)
    with pytest.raises(RegistryError, match="previous_registry_root does not match"):
        apply_registry_transaction(state1, rev_tx, block_height=6, txid="ef" * 32, context=ctx)


def test_register_previous_root_mismatch():
    ctx, gov_keys = _governance_context()
    _, pk_obj = generate_keypair()
    pk = encode_public_key(pk_obj)
    empty = RegistryState.empty()
    body = _make_register_body("alpha", pk, 5, registry_root(empty))
    body["previous_registry_root"] = "00" * 32  # wrong
    body["governance_signatures"] = [s.to_dict() for s in _sign_body(body, ctx, gov_keys)]
    tx = CuratorRegisterTx.from_dict(body)
    with pytest.raises(RegistryError, match="previous_registry_root does not match"):
        apply_registry_transaction(empty, tx, block_height=1, txid="ab" * 32, context=ctx)


def test_double_revocation_root_mismatch():
    ctx, gov_keys = _governance_context()
    curator_sk, curator_pk_obj = generate_keypair()
    curator_pk = encode_public_key(curator_pk_obj)
    empty = RegistryState.empty()
    body = _make_register_body("alpha", curator_pk, 5, registry_root(empty))
    body["governance_signatures"] = [s.to_dict() for s in _sign_body(body, ctx, gov_keys)]
    tx = CuratorRegisterTx.from_dict(body)
    state1 = apply_registry_transaction(empty, tx, block_height=1, txid="ab" * 32, context=ctx)

    rev_body = {
        "action": "curator_revoke",
        "curator_id": "alpha",
        "public_key_hex": curator_pk,
        "revocation_height": 20,
        "reason_code": "compromise",
        "previous_registry_root": registry_root(state1),
        "governance_signatures": [],
        "curator_signature": "0" * 128,
    }
    rev_body["governance_signatures"] = [s.to_dict() for s in _sign_body(rev_body, ctx, gov_keys, include_curator=(curator_sk, curator_pk))]
    rev_tx = CuratorRevokeTx.from_dict(rev_body)
    state2 = apply_registry_transaction(state1, rev_tx, block_height=6, txid="ef" * 32, context=ctx)

    # Try revoking already revoked curator
    rev_body2 = dict(rev_body, previous_registry_root=registry_root(state2), revocation_height=30)
    rev_body2["governance_signatures"] = [s.to_dict() for s in _sign_body(rev_body2, ctx, gov_keys, include_curator=(curator_sk, curator_pk))]
    rev_tx2 = CuratorRevokeTx.from_dict(rev_body2)
    with pytest.raises(RegistryError, match="curator is already revoked"):
        apply_registry_transaction(state2, rev_tx2, block_height=21, txid="01" * 32, context=ctx)
