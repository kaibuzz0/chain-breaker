"""Storage integration tests for reorg / canonical-tip switching."""

from __future__ import annotations

from pathlib import Path

from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block
from chainbreaker.registry_state import RegistryState
from chainbreaker.storage import FlatFileStorageBackend, recover_store


def _initial_state() -> RegistryState:
    return RegistryState.genesis(governance_keys=["0" * 64, "1" * 64], threshold=1)


def _simple_block(prev: BlockV2, nonce: int = 0, target: int | None = None) -> BlockV2:
    target = target if target is not None else prev.header.target
    header = BlockHeaderV2(
        version=2,
        prev_hash=prev.header.hash(),
        merkle_root="0" * 64,
        registry_root="0" * 64,
        timestamp=prev.header.timestamp + 600,
        target=target,
        nonce=nonce,
    )
    b = BlockV2(header=header, transactions=[])
    b.header.mine(max_iterations=1_000_000)
    return b


def test_read_chain_up_to(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        prev = genesis
        state = _initial_state()
        blocks: list[BlockV2] = []
        for _ in range(5):
            b = _simple_block(prev)
            state = backend.append_block(b, state)
            blocks.append(b)
            prev = b

        chain = backend.read_chain_up_to(3)
        assert len(chain) == 4  # genesis + 3
        assert chain[0].hash == genesis.hash
        # `prev` is now height 5; compare with the actual height-3 block.
        assert chain[3].hash == blocks[2].hash
    finally:
        backend.close()


def test_list_blocks(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        prev = genesis
        state = _initial_state()
        for _ in range(4):
            b = _simple_block(prev)
            state = backend.append_block(b, state)
            prev = b
        assert backend.list_blocks() == [1, 2, 3, 4]
    finally:
        backend.close()


def test_atomic_tip_switch(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        prev = genesis
        state = _initial_state()
        blocks: list[BlockV2] = []
        for _ in range(5):
            b = _simple_block(prev)
            state = backend.append_block(b, state)
            blocks.append(b)
            prev = b

        # Roll HEAD back to height 2 without deleting files
        result = backend.atomic_tip_switch(2, blocks[1].header.hash())
        assert result["new_tip_height"] == 2
        tip = backend.get_tip()
        assert tip["height"] == 2
        assert tip["block_hash"] == blocks[1].header.hash()

        # Orphaned block files still exist but are not in indexes
        assert backend.list_blocks() == [1, 2, 3, 4, 5]
        # Derived indexes only cover canonical heights
        assert result["rebuilt_indexes"]["tip_height"] == 2
        assert result["rebuilt_indexes"]["indexed_heights"] == [1, 2]
    finally:
        backend.close()


def test_rebuild_indexes(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        prev = genesis
        state = _initial_state()
        for _ in range(3):
            b = _simple_block(prev)
            state = backend.append_block(b, state)
            prev = b

        info = backend.rebuild_indexes()
        assert info["tip_height"] == 3
        assert info["indexed_heights"] == [1, 2, 3]
        assert (root / "indexes" / "height_to_hash.json").exists()
        assert (root / "indexes" / "hash_to_height.json").exists()
    finally:
        backend.close()


def test_recovery_after_tip_switch(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        prev = genesis
        state = _initial_state()
        blocks: list[BlockV2] = []
        for _ in range(4):
            b = _simple_block(prev)
            state = backend.append_block(b, state)
            blocks.append(b)
            prev = b

        backend.atomic_tip_switch(1, blocks[0].header.hash())
    finally:
        backend.close()

    result = recover_store(root, "test-net", genesis.header.hash())
    assert result["height"] == 1
    # recover_store returns the prev_hash of the lowest verified block, which for
    # a reorg-tipped chain at height 1 is the genesis hash.
    assert result["block_hash"] == genesis.header.hash()
