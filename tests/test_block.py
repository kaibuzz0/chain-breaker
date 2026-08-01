
from chainbreaker.block import (
    GENESIS_HASH,
    GENESIS_NONCE,
    MAX_TARGET,
    Block,
    BlockHeader,
    BlockV2,
    create_genesis_block,
    header_hash,
    satisfies_pow,
)
from chainbreaker.codec import BinaryCodec


def test_genesis_hardcoded():
    g = create_genesis_block()
    assert g.verify(allow_genesis=True)
    assert g.hash == GENESIS_HASH
    assert g.header.nonce == GENESIS_NONCE


def test_genesis_to_dict_roundtrip():
    g = create_genesis_block()
    g2 = BlockV2.from_dict(g.to_dict())
    assert g2.hash == g.hash


def test_header_hash_is_double_sha256():
    h = {
        "version": 1,
        "prev_hash": "0" * 64,
        "merkle_root": "a" * 64,
        "timestamp": 1,
        "target": "0" * 63 + "1",
        "nonce": 0,
    }
    from chainbreaker.crypto import HashEngine
    expected = HashEngine.hash_double_hex(BinaryCodec.encode_header(h))
    assert header_hash(h) == expected


def test_mine_block():
    header = BlockHeader(1, "0" * 64, "a" * 64, 1704067200, MAX_TARGET, 0)
    block = Block(header, [])
    assert block.mine(max_iterations=1_000_000)
    assert satisfies_pow(block.hash, MAX_TARGET)


def test_block_rejects_tampered_hash():
    g = create_genesis_block()
    bad = Block.from_dict(g.to_dict())
    bad.header.nonce += 1
    assert not bad.verify(allow_genesis=True)


def test_target_bounds():
    header = BlockHeader(1, "0" * 64, "a" * 64, 1704067200, MAX_TARGET + 1, 0)
    block = Block(header, [])
    assert not block.verify()
    header2 = BlockHeader(1, "0" * 64, "a" * 64, 1704067200, 0, 0)
    block2 = Block(header2, [])
    assert not block2.verify()
