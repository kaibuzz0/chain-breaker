"""Tests for Protocol v2 proof-of-work.

These tests verify the exact PoW rule, target encoding, mining loop, and
chain-work calculation defined in docs/POW_V2_SPECIFICATION.md.
"""

import pytest

from chainbreaker.block import (
    GENESIS_HASH,
    GENESIS_HEADER_BYTES,
    GENESIS_NONCE,
    GENESIS_TARGET,
    MAX_TARGET,
    MIN_TARGET,
    BlockHeaderV2,
    create_genesis_block,
    mine_header_v2,
    satisfies_pow,
)
from chainbreaker.codec import BinaryCodec
from chainbreaker.crypto import (
    HashEngine,
    check_pow_v2,
    hex_to_target,
    target_to_hex,
    work_for_target_v2,
)

# ---------------------------------------------------------------------------

# Target encoding vectors

# ---------------------------------------------------------------------------





def test_max_target_round_trip():

    assert hex_to_target(target_to_hex(MAX_TARGET)) == MAX_TARGET





def test_min_target_round_trip():

    assert hex_to_target(target_to_hex(MIN_TARGET)) == MIN_TARGET





def test_target_to_hex_is_big_endian_32_bytes():

    assert target_to_hex(0x00010203) == "0" * 56 + "00010203"

    assert len(bytes.fromhex(target_to_hex(0x00010203))) == 32





def test_hex_to_target_rejects_invalid_zero():

    assert hex_to_target("0" * 64) == 0





def test_target_out_of_range_rejected_by_validation():

    with pytest.raises(ValueError):

        work_for_target_v2(0)

    with pytest.raises(ValueError):

        work_for_target_v2(-1)





# ---------------------------------------------------------------------------

# Fixed PoW vectors

# ---------------------------------------------------------------------------





def test_genesis_header_bytes_hash_matches_genesis_hash():

    digest = HashEngine.hash_double(GENESIS_HEADER_BYTES)

    assert digest.hex() == GENESIS_HASH

    assert int.from_bytes(digest, "big") <= GENESIS_TARGET





def test_check_pow_v2_passes_on_genesis():

    assert check_pow_v2(GENESIS_HEADER_BYTES, GENESIS_TARGET)





def test_check_pow_v2_rejects_zero_nonce_genesis():

    header, _ = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)

    header["nonce"] = 0

    bad_bytes = BinaryCodec.encode_header_v2(header)

    assert not check_pow_v2(bad_bytes, GENESIS_TARGET)





def test_satisfies_pow_uses_hex_integer_comparison():

    assert satisfies_pow("0" * 64, MAX_TARGET)

    assert not satisfies_pow("f" * 64, MIN_TARGET)





def test_genesis_hash_satisfies_pow():

    assert satisfies_pow(GENESIS_HASH, GENESIS_TARGET)





# ---------------------------------------------------------------------------

# Header v2 mining

# ---------------------------------------------------------------------------





def test_mine_header_v2_finds_valid_nonce():

    header = BlockHeaderV2(

        version=2,

        prev_hash="a" * 64,

        merkle_root="b" * 64,

        registry_root="c" * 64,

        timestamp=1704067201,

        target=MAX_TARGET,

        nonce=0,

    )

    assert mine_header_v2(header, max_iterations=1_000_000, start_nonce=0)

    assert satisfies_pow(header.hash(), MAX_TARGET)





def test_mine_header_v2_respects_start_nonce():

    header = BlockHeaderV2(

        version=2,

        prev_hash="a" * 64,

        merkle_root="b" * 64,

        registry_root="c" * 64,

        timestamp=1704067201,

        target=MAX_TARGET,

        nonce=0,

    )

    assert mine_header_v2(header, max_iterations=1_000_000, start_nonce=1000)

    assert header.nonce >= 1000





def test_mine_header_v2_returns_false_when_impossible():

    header = BlockHeaderV2(

        version=2,

        prev_hash="a" * 64,

        merkle_root="b" * 64,

        registry_root="c" * 64,

        timestamp=1704067201,

        target=MIN_TARGET,

        nonce=0,

    )

    assert not mine_header_v2(header, max_iterations=1000)





def test_mine_header_v2_nonce_wraps_on_exhaustion():

    header = BlockHeaderV2(

        version=2,

        prev_hash="a" * 64,

        merkle_root="b" * 64,

        registry_root="c" * 64,

        timestamp=1704067201,

        target=MIN_TARGET,

        nonce=0xFFFFFFFFFFFFFFFE,

    )

    mine_header_v2(header, max_iterations=10)

    # After 10 increments starting at 0xFFFFFFFFFFFFFFFE:

    # 0xFFFFFFFFFFFFFFFE, 0xFFFFFFFFFFFFFFFF, 0, 1, 2, ..., 7

    assert header.nonce == 8





def test_block_header_v2_mine_method():

    header = BlockHeaderV2(

        version=2,

        prev_hash="a" * 64,

        merkle_root="b" * 64,

        registry_root="c" * 64,

        timestamp=1704067201,

        target=MAX_TARGET,

        nonce=0,

    )

    assert header.mine(max_iterations=1_000_000)

    assert satisfies_pow(header.hash(), MAX_TARGET)





def test_mine_header_v2_only_nonce_changes():

    header = BlockHeaderV2(

        version=2,

        prev_hash="a" * 64,

        merkle_root="b" * 64,

        registry_root="c" * 64,

        timestamp=1704067201,

        target=MAX_TARGET,

        nonce=0,

    )

    before = header.to_dict()

    mine_header_v2(header, max_iterations=1_000_000)

    after = header.to_dict()

    assert before["version"] == after["version"]

    assert before["prev_hash"] == after["prev_hash"]

    assert before["merkle_root"] == after["merkle_root"]

    assert before["registry_root"] == after["registry_root"]

    assert before["timestamp"] == after["timestamp"]

    assert before["target"] == after["target"]

    assert before["nonce"] != after["nonce"]





# ---------------------------------------------------------------------------

# Chain work

# ---------------------------------------------------------------------------





def test_work_max_target_is_one():

    assert work_for_target_v2(MAX_TARGET) == 1





def test_work_min_target_is_max_target():

    assert work_for_target_v2(MIN_TARGET) == MAX_TARGET





def test_work_increases_as_target_decreases():

    high_target = MAX_TARGET

    low_target = MAX_TARGET // 2

    assert work_for_target_v2(low_target) > work_for_target_v2(high_target)





def test_chain_work_sum():

    work1 = work_for_target_v2(MAX_TARGET)

    work2 = work_for_target_v2(MAX_TARGET // 2)

    assert work1 + work2 == 1 + 2





# ---------------------------------------------------------------------------

# Adversarial tests

# ---------------------------------------------------------------------------





def test_altered_nonce_invalidates_pow():

    header, _ = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)

    header["nonce"] = GENESIS_NONCE + 1

    bad = BinaryCodec.encode_header_v2(header)

    assert not check_pow_v2(bad, GENESIS_TARGET)





def test_altered_previous_hash_invalidates_pow():

    header, _ = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)

    header["prev_hash"] = "1" + "0" * 63

    bad = BinaryCodec.encode_header_v2(header)

    assert not check_pow_v2(bad, GENESIS_TARGET)





def test_altered_merkle_root_invalidates_pow():

    header, _ = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)

    header["merkle_root"] = "1" + "0" * 63

    bad = BinaryCodec.encode_header_v2(header)

    assert not check_pow_v2(bad, GENESIS_TARGET)





def test_altered_registry_root_invalidates_pow():

    header, _ = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)

    header["registry_root"] = "1" + "0" * 63

    bad = BinaryCodec.encode_header_v2(header)

    assert not check_pow_v2(bad, GENESIS_TARGET)





def test_altered_timestamp_invalidates_pow():

    header, _ = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)

    header["timestamp"] += 1

    bad = BinaryCodec.encode_header_v2(header)

    assert not check_pow_v2(bad, GENESIS_TARGET)





def test_altered_target_in_header_invalidates_pow():

    header, _ = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)

    # Swap target for a different valid target; the same nonce no longer wins.

    header["target"] = target_to_hex(MIN_TARGET)

    bad = BinaryCodec.encode_header_v2(header)

    assert not check_pow_v2(bad, MIN_TARGET)





def test_truncated_header_rejected():

    assert not check_pow_v2(GENESIS_HEADER_BYTES[:-1], GENESIS_TARGET)





def test_malformed_target_encoding_detected_by_hash():

    # Build a header with a target hex string that does not decode to 32 bytes.

    header, _ = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)

    header["target"] = "ffff"  # too short

    with pytest.raises(ValueError):

        BinaryCodec.encode_header_v2(header)





def test_wrong_byte_order_target_changes_pow_result():

    # Use the little-endian interpretation of the same target integer.

    le_target_hex = (GENESIS_TARGET).to_bytes(32, "little").hex()

    header, _ = BinaryCodec.decode_header_v2(GENESIS_HEADER_BYTES)

    header["target"] = le_target_hex

    bad = BinaryCodec.encode_header_v2(header)

    # The genesis nonce no longer wins against the byte-swapped target bytes.

    assert not check_pow_v2(bad, GENESIS_TARGET)





def test_v1_header_rejected_by_v2_validator():

    v1_header = bytes([0x01]) + b"" * 116

    with pytest.raises((ValueError, TypeError)):
        BinaryCodec.decode_header_v2(v1_header)





def test_v2_header_ignored_by_v1_validator():

    # A v2 header cannot be decoded as a valid v1 header because the byte

    # layouts are incompatible.  decode_header will parse the first 117 bytes

    # but leave the remaining 32 v2 bytes unconsumed.

    header, offset = BinaryCodec.decode_header(GENESIS_HEADER_BYTES)

    assert offset == 117

    assert header["version"] == 2

    assert len(GENESIS_HEADER_BYTES) > offset





# ---------------------------------------------------------------------------

# Genesis preservation

# ---------------------------------------------------------------------------





def test_create_genesis_block_does_not_re_mine():

    g = create_genesis_block()

    assert g.header.nonce == GENESIS_NONCE

    assert g.hash == GENESIS_HASH

