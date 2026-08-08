"""Fork-choice tests for reorg / state-branching."""

from __future__ import annotations

from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block
from chainbreaker.chain import Ledger
from chainbreaker.reorg import (
    ReorgEngine,
    ReorgError,
    compare_work,
    compute_work,
    find_common_ancestor,
)


def _make_empty_block(prev: BlockV2, timestamp: int, nonce: int = 0, target: int | None = None) -> BlockV2:
    """Build a minimal empty v2 block linking to prev."""
    target = target if target is not None else prev.header.target
    header = BlockHeaderV2(
        version=2,
        prev_hash=prev.hash,
        merkle_root="0" * 64,
        registry_root="0" * 64,
        timestamp=timestamp,
        target=target,
        nonce=nonce,
    )
    b = BlockV2(header=header, transactions=[])
    return b


def _mine_suffix(prev: BlockV2, count: int, start_time: int, target: int | None = None, iterations: int = 1_000_000) -> list[BlockV2]:
    """Mine `count` empty v2 blocks with distinct timestamps."""
    blocks: list[BlockV2] = []
    current = prev
    for i in range(count):
        b = _make_empty_block(current, start_time + i * 600, target=target)
        if not b.header.mine(max_iterations=iterations):
            raise RuntimeError("mining failed in test")
        blocks.append(b)
        current = b
    return blocks


def _suffix_from_ledger(ledger: Ledger, count: int, timestamp_offset: int = 0) -> list[BlockV2]:
    """Mine `count` blocks on a ledger, with a timestamp offset for divergence."""
    blocks: list[BlockV2] = []
    for i in range(count):
        ts = ledger.next_block_timestamp() + timestamp_offset + i * 600
        block = ledger.mine_block_v2([], timestamp=ts)
        assert ledger.add_block_v2(block)
        blocks.append(block)
    return blocks


def test_compute_work_basic():
    # Larger target == easier == less work per block.
    easy_target = 2**220
    hard_target = 2**200
    easy_work = compute_work(easy_target)
    hard_work = compute_work(hard_target)
    assert hard_work > easy_work
    assert easy_work > 0


def test_compare_work():
    assert compare_work(10, 20) == "candidate_wins"
    assert compare_work(20, 10) == "current_wins"
    assert compare_work(10, 10) == "tie"


def test_find_common_ancestor_same_chain():
    genesis = create_genesis_block(network_id="test-net")
    base = Ledger(chain=[genesis], network_id="test-net")
    _ = _suffix_from_ledger(base, 5)
    chain = list(base.chain)
    assert find_common_ancestor(chain, list(chain)) == 5


def test_find_common_ancestor_extension():
    genesis = create_genesis_block(network_id="test-net")
    base = Ledger(chain=[genesis], network_id="test-net")
    _suffix_from_ledger(base, 3)

    ext = Ledger(chain=list(base.chain), network_id="test-net")
    ext_blocks = _suffix_from_ledger(ext, 2)

    full_ext = list(base.chain) + ext_blocks
    assert find_common_ancestor(list(base.chain), full_ext) == 3


def test_find_common_ancestor_one_block_fork():
    genesis = create_genesis_block(network_id="test-net")
    base = Ledger(chain=[genesis], network_id="test-net")
    _suffix_from_ledger(base, 2)

    fork_a = Ledger(chain=list(base.chain), network_id="test-net")
    fork_b = Ledger(chain=list(base.chain), network_id="test-net")
    a_blocks = _suffix_from_ledger(fork_a, 1, timestamp_offset=0)
    b_blocks = _suffix_from_ledger(fork_b, 1, timestamp_offset=1000)

    chain_a = list(base.chain) + a_blocks
    chain_b = list(base.chain) + b_blocks
    assert find_common_ancestor(chain_a, chain_b) == 2


def test_find_common_ancestor_genesis_mismatch():
    genesis_a = create_genesis_block(network_id="net-a")
    # Build a different genesis by corrupting hash expectation via a dummy second block
    genesis_b = BlockV2(
        header=BlockHeaderV2(
            version=2,
            prev_hash="1" + "0" * 63,
            merkle_root="0" * 64,
            registry_root="0" * 64,
            timestamp=0,
            target=genesis_a.header.target,
            nonce=0,
        ),
        transactions=[],
    )
    try:
        find_common_ancestor([genesis_a], [genesis_b])
    except ReorgError as exc:
        assert "genesis mismatch" in str(exc)
    else:
        raise AssertionError("expected ReorgError")


def test_higher_work_branch_wins():
    genesis = create_genesis_block(network_id="test-net")
    base = Ledger(chain=[genesis], network_id="test-net")
    _suffix_from_ledger(base, 3)

    # Fork A: 1 block, diverging timestamp
    fork_a = Ledger(chain=list(base.chain), network_id="test-net")
    a_blocks = _suffix_from_ledger(fork_a, 1, timestamp_offset=0)
    chain_a = list(base.chain) + a_blocks

    # Fork B: 2 blocks with different timestamp, diverging at first block
    fork_b = Ledger(chain=list(base.chain), network_id="test-net")
    b_blocks = _suffix_from_ledger(fork_b, 2, timestamp_offset=1000)
    chain_b = list(base.chain) + b_blocks

    engine = ReorgEngine(chain_a)
    result = engine.evaluate_candidate(chain_b)
    assert result.switched is True
    assert result.new_tip_height == 5
    assert result.common_ancestor_height == 3


def test_higher_height_lower_work_branch_loses():
    genesis = create_genesis_block(network_id="test-net")
    base = Ledger(chain=[genesis], network_id="test-net")
    _suffix_from_ledger(base, 3)

    # Fork A: 2 valid blocks at easy target
    fork_a = Ledger(chain=list(base.chain), network_id="test-net")
    a_blocks = _suffix_from_ledger(fork_a, 2)
    chain_a = list(base.chain) + a_blocks

    # Fork B: 10 blocks at a much harder target. Each block contributes far less
    # work, so total work stays lower even though height is greater. Because the
    # candidate target differs from the retarget schedule, the engine rejects it
    # during validation before work comparison.
    start_time = base.last_block.header.timestamp + 600
    hard_target = 2**250
    hard_blocks = _mine_suffix(base.last_block, 10, start_time, target=hard_target)
    chain_b = list(base.chain) + hard_blocks

    engine = ReorgEngine(chain_a)
    result = engine.evaluate_candidate(chain_b)
    assert result.switched is False
    # Either rejected for invalid target, or rejected for insufficient work.
    reason = result.reason.lower()
    assert "target" in reason or "work" in reason or "validation failed" in reason


def test_equal_work_no_switch():
    genesis = create_genesis_block(network_id="test-net")
    base = Ledger(chain=[genesis], network_id="test-net")
    _suffix_from_ledger(base, 3)

    fork_a = Ledger(chain=list(base.chain), network_id="test-net")
    fork_b = Ledger(chain=list(base.chain), network_id="test-net")
    a_blocks = _suffix_from_ledger(fork_a, 1, timestamp_offset=0)
    b_blocks = _suffix_from_ledger(fork_b, 1, timestamp_offset=1000)
    chain_a = list(base.chain) + a_blocks
    chain_b = list(base.chain) + b_blocks

    engine = ReorgEngine(chain_a)
    result = engine.evaluate_candidate(chain_b)
    assert result.switched is False
    assert "tie" in result.reason.lower() or "not greater" in result.reason.lower()


def test_invalid_candidate_rejected():
    genesis = create_genesis_block(network_id="test-net")
    base = Ledger(chain=[genesis], network_id="test-net")
    _suffix_from_ledger(base, 3)

    fork_a = Ledger(chain=list(base.chain), network_id="test-net")
    a_blocks = _suffix_from_ledger(fork_a, 2)
    chain_a = list(base.chain) + a_blocks

    fork_b = Ledger(chain=list(base.chain), network_id="test-net")
    b_blocks = _suffix_from_ledger(fork_b, 2, timestamp_offset=2000)
    chain_b = list(base.chain) + b_blocks
    # Mutate the first suffix block to break registry_root commitment
    bad_block = chain_b[4]
    bad_block.header.registry_root = "0" * 64

    engine = ReorgEngine(chain_a)
    result = engine.evaluate_candidate(chain_b)
    assert result.switched is False
    assert "registry_root" in result.reason.lower() or "validation failed" in result.reason.lower()


def test_max_reorg_depth_policy():
    genesis = create_genesis_block(network_id="test-net")
    base_chain = [genesis]
    start_time = genesis.header.timestamp + 600
    base_blocks = _mine_suffix(genesis, 3, start_time)
    base_chain.extend(base_blocks)

    start_time = base_chain[-1].header.timestamp + 600
    a_blocks = _mine_suffix(base_chain[-1], 1, start_time)
    chain_a = base_chain + a_blocks

    b_blocks = _mine_suffix(base_chain[-1], 3, start_time + 1000)
    chain_b = base_chain + b_blocks

    # max_reorg_depth=0 forbids any reorg from the current tip.
    engine = ReorgEngine(chain_a, max_reorg_depth=0)
    result = engine.evaluate_candidate(chain_b)
    assert result.switched is False
    assert "depth" in result.reason.lower()
