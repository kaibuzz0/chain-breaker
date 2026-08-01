
import time

import pytest

from chainbreaker.chain import DIFFICULTY_RETARGET_INTERVAL, TARGET_BLOCK_TIME, Ledger
from chainbreaker.witness import CuratorSigner, Registry, verify_transaction_witnesses


def make_test_tx(curator, body_hash=None):
    body = {
        "schema": "chainbreaker-manifest-v1",
        "content_hash": body_hash or ("a" * 64),
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
    w = curator.sign_manifest(body)
    return {"version": 1, "type": "scripture", "body": body, "witnesses": [w]}


def make_ledger_with_curator():
    curator = CuratorSigner("alice")
    registry = Registry()
    registry.register(curator.as_curator())
    ledger = Ledger()

    def validator(t):
        return verify_transaction_witnesses(registry, t, block_height=ledger.height() + 1)

    ledger.transaction_validator = validator
    return ledger, curator


def test_genesis_chain_valid():
    ledger = Ledger()
    assert ledger.validate_chain()
    assert ledger.height() == 0


def test_mine_and_add_one_block():
    ledger, curator = make_ledger_with_curator()
    tx = make_test_tx(curator)
    block = ledger.mine_block([tx], max_iterations=1_000_000)
    assert ledger.add_block(block)
    assert ledger.validate_chain()
    assert ledger.height() == 1


def test_add_block_then_validate():
    """A block accepted by add_block must always pass validate_chain."""
    ledger, curator = make_ledger_with_curator()
    for _ in range(5):
        tx = make_test_tx(curator)
        block = ledger.mine_block([tx], max_iterations=1_000_000)
        assert ledger.add_block(block)
    assert ledger.validate_chain()


def test_retarget_boundary_consistency():
    ledger, curator = make_ledger_with_curator()
    base_ts = ledger.chain[0].header.timestamp
    # Use spacing that produces exactly the expected retarget window duration.
    spacing = TARGET_BLOCK_TIME * DIFFICULTY_RETARGET_INTERVAL / (DIFFICULTY_RETARGET_INTERVAL - 1)
    for i in range(1, DIFFICULTY_RETARGET_INTERVAL + 1):
        tx = make_test_tx(curator)
        ts = base_ts + int(i * spacing)
        block = ledger.mine_block([tx], max_iterations=2_000_000, timestamp=ts)
        assert ledger.add_block(block), f"failed at height {i}"
    assert ledger.validate_chain()
    # With exact average block spacing, target should remain unchanged at the boundary
    assert ledger.last_block.header.target == ledger.chain[0].header.target


def test_invalid_pow_rejected():
    ledger, curator = make_ledger_with_curator()
    tx = make_test_tx(curator)
    block = ledger.mine_block([tx], max_iterations=1_000_000)
    block.header.nonce += 1
    assert not ledger.add_block(block)


def test_wrong_prev_hash_rejected():
    ledger, curator = make_ledger_with_curator()
    tx = make_test_tx(curator)
    block = ledger.mine_block([tx], max_iterations=1_000_000)
    block.header.prev_hash = "0" * 64
    assert not ledger.add_block(block)


def test_altered_transaction_rejected():
    ledger, curator = make_ledger_with_curator()
    tx = make_test_tx(curator)
    block = ledger.mine_block([tx], max_iterations=1_000_000)
    block.transactions[0]["body"]["title"] = "tampered"
    assert not ledger.add_block(block)


def test_no_witness_rejected():
    ledger, curator = make_ledger_with_curator()
    body = {
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
    tx = {"version": 1, "type": "scripture", "body": body, "witnesses": []}
    with pytest.raises(ValueError):
        ledger.mine_block([tx], max_iterations=1)


def test_retroactive_validation_after_time_passes():
    """Historical blocks must remain valid even as wall clock advances."""
    ledger, curator = make_ledger_with_curator()
    for _ in range(3):
        tx = make_test_tx(curator)
        block = ledger.mine_block([tx], max_iterations=1_000_000)
        assert ledger.add_block(block)
    # Sleep a tiny amount; chain should still validate
    time.sleep(1)
    assert ledger.validate_chain()
