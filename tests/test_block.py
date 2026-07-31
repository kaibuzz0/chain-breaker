
import pytest

from chainbreaker.block import create_genesis_block, Block, BlockHeader
from chainbreaker.chain import Ledger
from chainbreaker.crypto import HashEngine


def test_genesis_verifies():
    g = create_genesis_block()
    assert g.verify(allow_genesis=True)


def test_genesis_timestamp_historical():
    g = create_genesis_block()
    assert g.header.timestamp == 1704067200


def test_fake_hash_deserialization_is_recomputed():
    g = create_genesis_block()
    header = BlockHeader(
        version=1,
        prev_hash=g.hash,
        merkle_root="0" * 64,
        timestamp=g.header.timestamp + 600,
        difficulty=g.header.difficulty,
        nonce=0,
    )
    block = Block(header=header, transactions=[])
    # Attacker supplies a fake stored hash with enough zeros
    forged_dict = block.to_dict()
    forged_dict["hash"] = "0" * 64
    reloaded = Block.from_dict(forged_dict)
    assert reloaded.hash != "0" * 64
    assert not reloaded.verify(median_past=g.header.timestamp)


def test_mine_and_extend():
    ledger = Ledger()
    tx = {"version": 1, "type": "test", "body": {"hello": "world"}, "witnesses": []}
    block = ledger.mine_block([tx], max_iterations=1_000_000)
    assert block.verify(median_past=ledger.chain[-2].header.timestamp)
    assert ledger.validate_chain()
