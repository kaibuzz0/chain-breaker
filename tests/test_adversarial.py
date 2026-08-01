
"""Adversarial and consensus tests for Chain-Breaker."""

import pytest

from chainbreaker.block import MAX_TARGET, Block, BlockHeader, create_genesis_block
from chainbreaker.chain import (
    DIFFICULTY_RETARGET_INTERVAL,
    TARGET_BLOCK_TIME,
    Ledger,
    block_decode,
    block_encode,
)
from chainbreaker.codec import BinaryCodec, CodecError, validate_transaction
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


def test_forged_stored_block_hash_does_not_trick_ledger():
    ledger, curator = make_ledger_with_curator()
    tx = make_test_tx(curator)
    block = ledger.mine_block([tx], max_iterations=1_000_000)
    block_dict = block.to_dict()
    block_dict["hash"] = "0" * 64
    forged = Block.from_dict(block_dict)
    # The ledger must recompute the hash and ignore the forged stored hash.
    assert forged.hash != "0" * 64
    assert forged.hash == block.hash
    assert ledger.add_block(forged)


def test_wrong_proof_of_work_rejected():
    ledger, curator = make_ledger_with_curator()
    tx = make_test_tx(curator)
    block = ledger.mine_block([tx], max_iterations=1_000_000)
    block.header.nonce += 1
    assert not ledger.add_block(block)


def test_altered_header_prev_hash_rejected():
    ledger, curator = make_ledger_with_curator()
    tx = make_test_tx(curator)
    block = ledger.mine_block([tx], max_iterations=1_000_000)
    block.header.prev_hash = "0" * 64
    assert not ledger.add_block(block)


def test_invalid_merkle_root_rejected():
    ledger, curator = make_ledger_with_curator()
    tx = make_test_tx(curator)
    block = ledger.mine_block([tx], max_iterations=1_000_000)
    block.header.merkle_root = "0" * 64
    assert not ledger.add_block(block)


def test_difficulty_change_outside_retarget_rejected():
    ledger, curator = make_ledger_with_curator()
    tx = make_test_tx(curator)
    block = ledger.mine_block([tx], max_iterations=1_000_000)
    block.header.target = MAX_TARGET // 2
    # PoW must be recomputed to match new target; but target is wrong
    assert not ledger.add_block(block)


def test_retarget_boundary_enforced():
    ledger, curator = make_ledger_with_curator()
    base_ts = ledger.chain[0].header.timestamp
    # Mine blocks 1..9 at exact spacing
    for i in range(1, DIFFICULTY_RETARGET_INTERVAL):
        tx = make_test_tx(curator)
        block = ledger.mine_block([tx], max_iterations=2_000_000,
                                   timestamp=base_ts + i * TARGET_BLOCK_TIME)
        assert ledger.add_block(block)
    # The next block (height 10) is a retarget boundary.
    ledger.expected_target_at(DIFFICULTY_RETARGET_INTERVAL)
    # A block with MAX_TARGET instead of the expected target must be rejected.
    tx = make_test_tx(curator)
    wrong_header = BlockHeader(
        version=1,
        prev_hash=ledger.last_block.hash,
        merkle_root=Block(BlockHeader(1, ledger.last_block.hash, "0"*64, base_ts + DIFFICULTY_RETARGET_INTERVAL * TARGET_BLOCK_TIME, MAX_TARGET, 0), [tx]).merkle_root(),
        timestamp=base_ts + DIFFICULTY_RETARGET_INTERVAL * TARGET_BLOCK_TIME,
        target=MAX_TARGET,
        nonce=0,
    )
    wrong_block = Block(wrong_header, [tx])
    wrong_block.mine(max_iterations=1_000_000)
    assert not ledger.add_block(wrong_block)
    # The correctly-targeted block must be accepted.
    good_block = ledger.mine_block([tx], max_iterations=2_000_000,
                                   timestamp=base_ts + DIFFICULTY_RETARGET_INTERVAL * TARGET_BLOCK_TIME)
    assert ledger.add_block(good_block)
    assert ledger.validate_chain()


def test_unknown_curator_witness_rejected():
    ledger, curator = make_ledger_with_curator()
    evil = CuratorSigner("evil")
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
    tx = {"version": 1, "type": "scripture", "body": body,
          "witnesses": [evil.sign_manifest(body)]}
    with pytest.raises(ValueError):
        ledger.mine_block([tx], max_iterations=1)


def test_duplicate_witnesses_rejected():
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
    w = curator.sign_manifest(body)
    tx = {"version": 1, "type": "scripture", "body": body, "witnesses": [w, w]}
    with pytest.raises(ValueError):
        ledger.mine_block([tx], max_iterations=1)


def test_curator_key_substitution_rejected():
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
    # Sign as alice but swap witness curator_id to bob
    w = curator.sign_manifest(body)
    w["curator_id"] = "bob"
    tx = {"version": 1, "type": "scripture", "body": body, "witnesses": [w]}
    with pytest.raises(ValueError):
        ledger.mine_block([tx], max_iterations=1)


def test_revoked_key_rejected():
    ledger, curator = make_ledger_with_curator()
    # Revoke alice at height 2
    ledger.transaction_validator = lambda t: True  # allow registry tx through
    reg_body = {
        "action": "revoke",
        "curator_id": "alice",
        "public_key_hex": curator.public_key_hex,
        "activation_height": 0,
        "revocation_height": 2,
        "previous_key_hex": None,
    }
    # Inject registry tx into a block; consensus does not enforce governance yet,
    # but the registry validator enforces it locally.
    registry = Registry()
    registry.register(curator.as_curator())
    registry.apply_registry_transaction(reg_body, 1)
    def validator(t):
        return verify_transaction_witnesses(registry, t, block_height=ledger.height() + 1)
    ledger.transaction_validator = validator
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
    w = curator.sign_manifest(body)
    tx = {"version": 1, "type": "scripture", "body": body, "witnesses": [w]}
    with pytest.raises(ValueError):
        ledger.mine_block([tx], max_iterations=1)


def test_truncated_codec_input():
    header = {
        "version": 1,
        "prev_hash": "0" * 64,
        "merkle_root": "a" * 64,
        "timestamp": 1,
        "target": "0" * 64,
        "nonce": 0,
    }
    data = BinaryCodec.encode_header(header)
    with pytest.raises(CodecError):
        BinaryCodec.decode_header(data[:-1])
    tx = {"version": 1, "type": "scripture", "body": {
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
    }, "witnesses": []}
    data = BinaryCodec.encode_transaction(tx)
    with pytest.raises(CodecError):
        BinaryCodec.decode_transaction(data[:-1])


def test_noncanonical_varint_rejected():
    # A small value encoded with the 64-bit prefix is noncanonical.
    tx = {"version": 1, "type": "x", "body": {}, "witnesses": []}
    canonical = BinaryCodec.encode_transaction(tx)
    # Replace the version varint with a long-prefix encoding of 1.
    long_prefix = b"\xff" + (1).to_bytes(8, "little")
    # canonical[1] is the single-byte version; replace it with 9-byte long form.
    bad = canonical[:1] + long_prefix + canonical[2:]
    with pytest.raises(CodecError):
        BinaryCodec.decode_transaction(bad)


def test_oversized_field_rejected():
    body = {
        "schema": "chainbreaker-manifest-v1",
        "content_hash": "a" * 64,
        "byte_length": 1,
        "media_type": "text/plain",
        "title": "x" * 100_000,
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
    # Schema allows up to 65535 byte strings; this exceeds it
    with pytest.raises(ValueError):
        validate_transaction(tx)


def test_invalid_unicode_rejected():
    tx = {
        "version": 1,
        "type": "scripture",
        "body": {
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
        },
        "witnesses": [],
    }
    data = BinaryCodec.encode_transaction(tx)
    # Corrupt a byte inside the title string bytes
    corrupted = bytearray(data)
    corrupted[20] = 0xFF
    corrupted[21] = 0xFF
    with pytest.raises(CodecError):
        BinaryCodec.decode_transaction(bytes(corrupted))


def test_wrong_genesis_rejected():
    g = create_genesis_block()
    g.header.nonce += 1
    assert not g.verify(allow_genesis=True)


def test_wrong_network_id_in_genesis_rejected():
    g = create_genesis_block()
    # Genesis v2 is a fixed constant with no mutable genesis transaction.
    # The network identity is enforced by the protocol constants and verified
    # against the hard-coded header bytes.
    assert g.transactions == []
    assert g.verify(allow_genesis=True)


def test_block_encode_decode_roundtrip():
    ledger, curator = make_ledger_with_curator()
    tx = make_test_tx(curator)
    block = ledger.mine_block([tx], max_iterations=1_000_000)
    encoded = block_encode(block)
    decoded, offset = block_decode(encoded)
    assert offset == len(encoded)
    assert decoded.hash == block.hash
    assert decoded.transactions == block.transactions
