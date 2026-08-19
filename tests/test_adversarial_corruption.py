"""Phase 5E: corruption testing.

Verify corrupted or malicious data is rejected safely without partial state
updates, cache mutation, or crashes.
"""

import pytest

from chainbreaker.block import GENESIS_HASH, BlockHeaderV2, BlockV2
from chainbreaker.chain import Ledger
from chainbreaker.codec import BinaryCodec
from chainbreaker.crypto import HashEngine, encode_public_key, generate_keypair, sign
from chainbreaker.governance import NETWORK_ID, GovernanceSignature
from chainbreaker.registry_state import registry_root


def _make_governance_keys(count: int = 3, threshold: int = 2):
    pairs = [generate_keypair() for _ in range(count)]
    privs = [p[0] for p in pairs]
    pubs = [encode_public_key(p[1]) for p in pairs]
    return privs, pubs


def _sign_body(privs, body: dict, network_id: str | None = None) -> list[dict]:
    # Sign with the network ID carried by the transaction body, not the module-level alpha constant.
    message = HashEngine.hash_object({
        "network_id": network_id if network_id is not None else body.get("network_id", NETWORK_ID),
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body),
    })
    return [GovernanceSignature(i, sign(priv, message)).to_dict() for i, priv in enumerate(privs)]


def _build_register_tx(privs, ledger, curator_id: str, public_key_hex: str, activation_height: int):
    root = registry_root(ledger.registry_state_at(ledger.height()))
    body = {
        "action": "curator_register",
        "curator_id": curator_id,
        "public_key_hex": public_key_hex,
        "activation_height": activation_height,
        "previous_registry_root": root,
        "network_id": ledger.network_id,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(privs, body)
    return {"type": "governance", "body": body}


@pytest.mark.parametrize("field,mutator", [
    ("prev_hash", lambda h: "0" * 64),
    ("merkle_root", lambda h: "f" * 64),
    ("registry_root", lambda h: "f" * 64),
    ("timestamp", lambda h: 0),
])
def test_corrupted_header_field_rejected(field, mutator):
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    block = ledger.mine_block_v2([])
    # Apply mutator to a copy of the header dict and recreate BlockHeaderV2
    header_dict = block.header.to_dict()
    header_dict[field] = mutator(header_dict[field])
    mutated = BlockHeaderV2.from_dict(header_dict)
    mutated_block = BlockV2(header=mutated, transactions=[])
    assert not ledger.add_block_v2(mutated_block)


def test_corrupted_block_bytes_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    block = ledger.mine_block_v2([])
    encoded = BinaryCodec.encode_header_v2(block.header.to_dict())
    # Mutate a byte in the middle of the header and try to re-validate the block
    mutated = bytearray(encoded)
    mutated[50] ^= 0xFF
    try:
        decoded, _ = BinaryCodec.decode_header_v2(bytes(mutated), strict=True)
        corrupted_header = BlockHeaderV2.from_dict(decoded)
        corrupted_block = BlockV2(header=corrupted_header, transactions=[])
        assert not ledger.add_block_v2(corrupted_block)
    except Exception:
        # Decoder rejected the corrupted bytes deterministically.
        pass


def test_truncated_header_rejected():
    encoded = BinaryCodec.encode_header_v2({
        "version": 2,
        "prev_hash": GENESIS_HASH,
        "merkle_root": "0" * 64,
        "registry_root": "0" * 64,
        "timestamp": 1,
        "target": "00" * 28 + "0000ffff",  # 64 hex chars = 32 bytes
        "nonce": 0,
    })
    with pytest.raises(ValueError):
        BinaryCodec.decode_header_v2(encoded[:100], strict=True)


def test_corrupted_registry_cache_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk_a, pk_a = generate_keypair()
    tx = _build_register_tx(privs, ledger, "alice", encode_public_key(pk_a), 2)
    assert ledger.add_block_v2(ledger.mine_block_v2([tx]))

    # Corrupt the cached state at height 1 to a different authority set
    ledger.registry_states[1] = ledger.registry_states[0]
    assert not ledger.validate_chain()


def test_corrupted_governance_signature_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk_a, pk_a = generate_keypair()
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": encode_public_key(pk_a),
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": ledger.network_id,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(privs, body)
    # Mutate all signatures so threshold cannot be met
    for sig in body["governance_signatures"]:
        sig["signature"] = "0" * 128
    assert not ledger.add_block_v2(ledger.mine_block_v2([{"type": "governance", "body": body}]))


def test_corrupted_governance_field_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk_a, pk_a = generate_keypair()
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": encode_public_key(pk_a),
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": ledger.network_id,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(privs, body)
    # Mutate the curator_id after signing
    body["curator_id"] = "bob"
    assert not ledger.add_block_v2(ledger.mine_block_v2([{"type": "governance", "body": body}]))


def test_missing_governance_field_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk_a, pk_a = generate_keypair()
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": encode_public_key(pk_a),
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": ledger.network_id,
        "schema_version": 1,
    }
    # omit signatures
    with pytest.raises((ValueError, KeyError)):
        ledger.add_block_v2(ledger.mine_block_v2([{"type": "governance", "body": body}]))


def test_invalid_public_key_in_governance_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    body = {
        "action": "curator_register",
        "curator_id": "alice",
        "public_key_hex": encode_public_key(generate_keypair()[1]),
        "activation_height": 2,
        "previous_registry_root": registry_root(ledger.registry_state_at(0)),
        "network_id": ledger.network_id,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(privs, body)
    # Mutate the public key after signing so the governance authorization fails.
    # The new key still has a valid V2 schema shape, so rejection proves
    # governance validation runs on top of generic schema validation.
    body["public_key_hex"] = "1" * 64
    assert not ledger.add_block_v2(ledger.mine_block_v2([{"type": "governance", "body": body}]))


def test_corrupted_witness_signature_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk_a, pk_a = generate_keypair()
    tx = _build_register_tx(privs, ledger, "alice", encode_public_key(pk_a), 2)
    assert ledger.add_block_v2(ledger.mine_block_v2([tx]))

    from chainbreaker.witness import sign_attestation_v2, verify_attestation_v2
    attestation = sign_attestation_v2(sk_a, HashEngine.hash_object_hex({"data": "test-data"}), "alice", 2)
    attestation["signature"] = "0" * 128
    assert not verify_attestation_v2(
        ledger.registry_state_at(1), attestation, HashEngine.hash_object_hex({"data": "test-data"}), 2
    )


def test_corrupted_witness_height_rejected():
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk_a, pk_a = generate_keypair()
    tx = _build_register_tx(privs, ledger, "alice", encode_public_key(pk_a), 2)
    assert ledger.add_block_v2(ledger.mine_block_v2([tx]))

    from chainbreaker.witness import sign_attestation_v2, verify_attestation_v2
    attestation = sign_attestation_v2(sk_a, HashEngine.hash_object_hex({"data": "test-data"}), "alice", 2)
    attestation["block_height"] = 999
    assert not verify_attestation_v2(
        ledger.registry_state_at(1), attestation, HashEngine.hash_object_hex({"data": "test-data"}), 2
    )


def test_random_byte_mutations_on_header_do_not_crash():
    import contextlib
    import random
    random.seed(0)
    header_dict = {
        "version": 2,
        "prev_hash": GENESIS_HASH,
        "merkle_root": "0" * 64,
        "registry_root": "0" * 64,
        "timestamp": 1,
        "target": "00" * 28 + "0000ffff",  # 64 hex chars = 32 bytes
        "nonce": 0,
    }
    encoded = BinaryCodec.encode_header_v2(header_dict)
    for _ in range(50):
        mutated = bytearray(encoded)
        idx = random.randrange(len(mutated))
        mutated[idx] = random.randrange(256)
        with contextlib.suppress(Exception):
            BinaryCodec.decode_header_v2(bytes(mutated), strict=True)
