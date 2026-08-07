"""Tests for the flat-file storage backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block
from chainbreaker.registry_state import RegistryState
from chainbreaker.storage import FlatFileStorageBackend
from chainbreaker.storage.filesystem import StorageIOError


def _make_simple_block(prev_block: BlockV2, nonce: int = 0) -> BlockV2:
    header = BlockHeaderV2(
        version=2,
        prev_hash=prev_block.header.hash(),
        merkle_root="0" * 64,
        registry_root="0" * 64,
        timestamp=prev_block.header.timestamp + 600,
        target=2 ** 220,
        nonce=nonce,
    )
    return BlockV2(header=header, transactions=[])


def test_storage_initializes_with_genesis(tmp_path: Path):
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash="0" * 64,
    )
    tip = backend.get_tip()
    assert tip["height"] == 0
    assert tip["block_hash"] == "0" * 64
    backend.close()


def test_storage_append_and_read_block(tmp_path: Path):
    root = tmp_path / "chain"
    genesis = create_genesis_block(network_id="test-net")
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    initial_state = RegistryState.genesis(
        governance_keys=["0" * 64, "1" * 64],
        threshold=1,
    )
    block = _make_simple_block(genesis)
    block.header.mine(max_iterations=100_000)
    new_state = backend.append_block(block, initial_state)

    assert backend.get_tip()["height"] == 1
    assert backend.get_tip()["block_hash"] == block.header.hash()
    read = backend.read_block(1)
    assert read.header.hash() == block.header.hash()
    assert new_state.threshold == initial_state.threshold
    backend.close()


def test_storage_missing_block_raises(tmp_path: Path):
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash="0" * 64,
    )
    with pytest.raises(StorageIOError):
        backend.read_block(1)
    backend.close()
