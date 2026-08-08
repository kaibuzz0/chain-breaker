"""Snapshot semantics during reorgs."""

from __future__ import annotations

from pathlib import Path

from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block
from chainbreaker.registry_state import RegistryState
from chainbreaker.storage import FlatFileStorageBackend


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


def test_snapshot_from_winning_branch_reused_safely(tmp_path: Path):
    """A snapshot created on the winning branch is usable for replay."""
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

        # Write a snapshot at the tip
        backend.write_snapshot(5, state)
        loaded = backend.read_snapshot(5)
        assert loaded is not None
        assert RegistryState.genesis(list(loaded.governance_keys), loaded.threshold) == _initial_state()
    finally:
        backend.close()


def test_orphaned_snapshot_not_trusted_as_canonical(tmp_path: Path):
    """A snapshot above the new HEAD must not be treated as canonical state."""
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

        # Snapshot the full tip
        backend.write_snapshot(5, state)

        # Reorg HEAD back to height 2
        backend.atomic_tip_switch(2, blocks[1].header.hash())

        # The old snapshot at height 5 is still on disk but corresponds to an
        # orphaned branch. read_snapshot should refuse to return it as canonical.
        loaded = backend.read_snapshot(5)
        assert loaded is None
    finally:
        backend.close()


def test_snapshot_after_reorg_matches_new_head(tmp_path: Path):
    """A snapshot written after a reorg must match the new canonical HEAD."""
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

        # Snapshot at height 4
        backend.write_snapshot(4, state)

        # Roll back to height 2 and snapshot the new canonical state
        backend.atomic_tip_switch(2, blocks[1].header.hash())
        # Snapshot the new canonical state at height 2.
        state_2 = _initial_state()
        backend.write_snapshot(2, state_2)
        loaded = backend.read_snapshot(2)
        assert loaded is not None
        assert loaded == state_2
        # Snapshot at height 4 is orphaned
        assert backend.read_snapshot(4) is None
    finally:
        backend.close()
