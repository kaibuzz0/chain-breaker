"""Phase 8M-A: Consensus Validation Hardening regression tests.

These tests verify that generic V2 transaction schema validation is
mandatory on every consensus acceptance path and that governance/optional
validators remain layered on top of the baseline.
"""

import json

import pytest

from chainbreaker.block import BlockHeaderV2, BlockV2
from chainbreaker.chain import Ledger
from chainbreaker.codec import BinaryCodec, SchemaError, validate_v2_transaction
from chainbreaker.crypto import HashEngine, MerkleTree, encode_public_key, generate_keypair, sign
from chainbreaker.governance import NETWORK_ID, GovernanceSignature
from chainbreaker.network.messages import BlockMessage
from chainbreaker.network.relay.engine import RelayEngine
from chainbreaker.network.relay.limits import RelayLimitPolicy
from chainbreaker.network.sync.block_sync import BlockSync
from chainbreaker.registry_state import registry_root
from chainbreaker.storage import FlatFileStorageBackend


def _make_governance_keys(count: int = 3, threshold: int = 2):
    pairs = [generate_keypair() for _ in range(count)]
    privs = [p[0] for p in pairs]
    pubs = [encode_public_key(p[1]) for p in pairs]
    return privs, pubs


def _sign_body(privs, body: dict) -> list[dict]:
    # Sign over the transaction body's actual network_id, which may be a derived
    # test identity rather than the alpha constant.
    message = HashEngine.hash_object({
        "network_id": body.get("network_id", NETWORK_ID),
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body),
    })
    return [GovernanceSignature(i, sign(priv, message)).to_dict() for i, priv in enumerate(privs)]


def _build_register_tx(privs, ledger: Ledger, curator_id: str, public_key_hex: str, activation_height: int):
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


def _mine_bad_block(ledger: Ledger, transactions: list[dict]) -> BlockV2:
    """Build a structurally valid v2 block whose transactions fail baseline
    schema validation.  This simulates a peer that mines outside the normal
    ``Ledger.mine_block_v2`` path (which now rejects malformed transactions)."""
    tx_hashes = [HashEngine.hash_object(tx) for tx in transactions]
    merkle_root_hex = HashEngine.hex(MerkleTree(tx_hashes).root or bytes(32))
    previous_state = ledger.registry_state_at(ledger.height())
    header = BlockHeaderV2(
        version=2,
        prev_hash=ledger.last_block.hash,
        merkle_root=merkle_root_hex,
        registry_root=registry_root(previous_state),
        timestamp=ledger.next_block_timestamp(),
        target=ledger.expected_target_at(ledger.height() + 1),
        nonce=0,
    )
    header.mine()
    return BlockV2(header=header, transactions=transactions)


def _block_message_payload(block: BlockV2) -> bytes:
    block_json = json.dumps(block.to_dict(), sort_keys=True, separators=(",", ":"))
    return BlockMessage(blocks=[{
        "hash": block.hash,
        "block_bytes": block_json.encode("utf-8").hex(),
    }]).to_payload()


# ---------------------------------------------------------------------------
# 1. Malformed transaction rejected by BlockV2.verify()
# ---------------------------------------------------------------------------

def test_block_v2_verify_rejects_malformed_transaction():
    """A block containing a transaction that fails baseline V2 schema
    validation must fail BlockV2.verify()."""
    ledger = Ledger(governance_keys=["0" * 64], governance_threshold=1)
    bad_block = _mine_bad_block(ledger, [{"type": "unknown", "body": {}}])
    assert not bad_block.verify(  # nosec B101
        reference_time=bad_block.header.timestamp + 100,
        median_past=0,
        expected_target=bad_block.header.target,
    )


# ---------------------------------------------------------------------------
# 2. Malformed transaction rejected by Ledger.add_block_v2()
# ---------------------------------------------------------------------------

def test_add_block_v2_rejects_malformed_transaction():
    """A ledger without an external transaction_validator must still reject
    blocks containing malformed transactions."""
    ledger = Ledger(governance_keys=["0" * 64], governance_threshold=1)
    bad_block = _mine_bad_block(ledger, [{"not_a_valid_envelope": True}])
    assert not ledger.add_block_v2(bad_block)  # nosec B101


# ---------------------------------------------------------------------------
# 3. Malformed transaction rejected during chain replay
# ---------------------------------------------------------------------------

def test_validate_chain_rejects_malformed_transaction():
    """validate_chain() must detect a malformed transaction that was inserted
    into the chain list, even with no external validator."""
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    good_block = ledger.mine_block_v2([])
    ledger.add_block_v2(good_block)

    mutated_chain = list(ledger.chain)
    bad_block = _mine_bad_block(ledger, [{"type": "governance"}])  # body missing
    mutated_chain[1] = bad_block
    replay = Ledger(chain=mutated_chain, governance_keys=pubs, governance_threshold=2)
    assert not replay.validate_chain()  # nosec B101


# ---------------------------------------------------------------------------
# 4. Malformed transaction arriving through sync rejected
# ---------------------------------------------------------------------------

def test_sync_rejects_malformed_transaction(tmp_path):
    """BlockSync + ledger.add_block_v2 (the sync validation convergence point)
    must reject a block with a malformed transaction."""
    privs, pubs = _make_governance_keys()
    honest = Ledger(governance_keys=pubs, governance_threshold=2)
    victim = Ledger(governance_keys=pubs, governance_threshold=2)
    block_sync = BlockSync(ledger=victim)

    bad_block = _mine_bad_block(honest, [{"type": "governance", "body": {"junk": True}}])
    payload = _block_message_payload(bad_block)
    msg = BlockMessage.from_payload(payload)

    parsed = block_sync.parse_block_message(
        msg,
        expected_height=victim.height() + 1,
        expected_prev_hash=victim.last_block.hash,
    )
    # Sync path converges on ledger.add_block_v2, which runs mandatory validation.
    assert not victim.add_block_v2(parsed)  # nosec B101


# ---------------------------------------------------------------------------
# 5. Malformed transaction arriving through relay rejected
# ---------------------------------------------------------------------------

def test_relay_rejects_malformed_transaction(tmp_path):
    """RelayEngine.handle_block() must reject a block with a malformed
    transaction before storage append."""
    privs, pubs = _make_governance_keys()
    honest = Ledger(governance_keys=pubs, governance_threshold=2)
    victim = Ledger(governance_keys=pubs, governance_threshold=2)
    storage = FlatFileStorageBackend(
        chain_root=tmp_path / "chain",
        network_id="chainbreaker-scripture-v2",
        genesis_hash=honest.genesis_hash(),
    )
    relay = RelayEngine(ledger=victim, storage=storage, limits=RelayLimitPolicy())

    bad_block = _mine_bad_block(honest, [{"type": "scripture", "body": {"missing": "fields"}}])
    payload = _block_message_payload(bad_block)
    result = relay.handle_block("peer-1", payload)
    assert any(r["status"] == "invalid" and r["hash"] == bad_block.hash for r in result["results"])  # nosec B101


# ---------------------------------------------------------------------------
# 6. Optional/custom validator cannot bypass baseline validation
# ---------------------------------------------------------------------------

def test_custom_validator_cannot_bypass_baseline_validation():
    """Even if a custom transaction_validator returns True, baseline schema
    validation must still reject malformed transactions."""
    ledger = Ledger(
        governance_keys=["0" * 64],
        governance_threshold=1,
        transaction_validator=lambda _tx: True,
    )
    bad_block = _mine_bad_block(ledger, [{"version": 1, "type": "nope", "body": {}, "witnesses": []}])
    assert not ledger.add_block_v2(bad_block)  # nosec B101


# ---------------------------------------------------------------------------
# 7. Governance transaction with valid schema but invalid authorization rejected
# ---------------------------------------------------------------------------

def test_governance_authorization_still_rejected_with_valid_schema():
    """Generic schema validation passes, but governance authorization must
    still reject a transaction signed over the wrong body."""
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk_a, pk_a = generate_keypair()
    tx = _build_register_tx(privs, ledger, "alice", encode_public_key(pk_a), 2)
    # Mutate body after signing so signatures are invalid but schema is fine.
    tx["body"]["curator_id"] = "bob"
    assert not ledger.add_block_v2(ledger.mine_block_v2([tx]))  # nosec B101


# ---------------------------------------------------------------------------
# 8. Valid existing V2 transactions remain accepted
# ---------------------------------------------------------------------------

def test_valid_governance_transaction_accepted():
    """A correctly formed and authorized governance transaction must still be
    accepted by the ledger."""
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk_a, pk_a = generate_keypair()
    tx = _build_register_tx(privs, ledger, "alice", encode_public_key(pk_a), 2)
    assert ledger.add_block_v2(ledger.mine_block_v2([tx]))  # nosec B101
    assert ledger.validate_chain()  # nosec B101


# ---------------------------------------------------------------------------
# 9. mine_block_v2 validates transactions symmetrically with mine_block V1
# ---------------------------------------------------------------------------

def test_mine_block_v2_rejects_malformed_transaction():
    """mine_block_v2() must reject malformed transactions before mining,
    matching the validation behavior of the deprecated mine_block()."""
    ledger = Ledger(governance_keys=["0" * 64], governance_threshold=1)
    with pytest.raises(SchemaError):
        ledger.mine_block_v2([{"not_a_valid_envelope": True}])


def test_validate_v2_transaction_accepts_canonical_wire_form():
    """Transactions encoded by BinaryCodec (version/type/body/witnesses) must
    pass validate_v2_transaction because the consensus path may receive them
    from network or storage decoding."""
    tx = {
        "version": 1,
        "type": "genesis",
        "body": {"network_id": "chainbreaker-scripture-v2", "message": "x", "timestamp": 1},
        "witnesses": [],
    }
    encoded = BinaryCodec.encode_transaction(tx)
    decoded, _ = BinaryCodec.decode_transaction(encoded)
    validate_v2_transaction(decoded)
