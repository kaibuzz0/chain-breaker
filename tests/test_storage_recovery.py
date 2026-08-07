"""Tests for storage corruption and recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block
from chainbreaker.registry_state import RegistryState
from chainbreaker.storage import FlatFileStorageBackend, recover_store
from chainbreaker.storage.filesystem import StorageIOError


def _simple_block(prev: BlockV2, nonce: int = 0) -> BlockV2:
    header = BlockHeaderV2(
        version=2,
        prev_hash=prev.header.hash(),
        merkle_root="0" * 64,
        registry_root="0" * 64,
        timestamp=prev.header.timestamp + 600,
        target=2 ** 220,
        nonce=nonce,
    )
    b = BlockV2(header=header, transactions=[])
    b.header.mine(max_iterations=100_000)
    return b


def _initial_state() -> RegistryState:
    return RegistryState.genesis(
        governance_keys=["0" * 64, "1" * 64],
        threshold=1,
    )


def _append_chain(root: Path, count: int) -> tuple[BlockV2, RegistryState]:
    genesis = create_genesis_block(network_id="test-net")
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    state = _initial_state()
    prev = genesis
    for _ in range(count):
        b = _simple_block(prev)
        state = backend.append_block(b, state)
        prev = b
    backend.close()
    return prev, state


def test_recovery_after_clean_shutdown(tmp_path: Path):
    root = tmp_path / "chain"
    tip, _state = _append_chain(root, 3)
    result = recover_store(root, "test-net", create_genesis_block(network_id="test-net").header.hash())
    assert result["height"] == 3


def test_recovery_truncates_block_file(tmp_path: Path):
    root = tmp_path / "chain"
    tip, _state = _append_chain(root, 3)
    block_path = root / "blocks" / "0000000002.bin"
    data = block_path.read_bytes()
    block_path.write_bytes(data[: len(data) // 2])

    result = recover_store(root, "test-net", create_genesis_block(network_id="test-net").header.hash())
    assert result["height"] == 1


def test_recovery_missing_head_recovers_to_genesis(tmp_path: Path):
    root = tmp_path / "chain"
    _append_chain(root, 2)
    head_path = root / "HEAD"
    head_path.unlink()

    result = recover_store(root, "test-net", create_genesis_block(network_id="test-net").header.hash())
    assert result["height"] == 0


def test_recovery_head_ahead_of_commits(tmp_path: Path):
    root = tmp_path / "chain"
    genesis = create_genesis_block(network_id="test-net")
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    state = _initial_state()
    b = _simple_block(genesis)
    backend.append_block(b, state)
    # Manually move HEAD forward without a corresponding block.
    (root / "HEAD").write_text(
        f"00000000000000000005:{b.header.hash()}:test-net:{genesis.header.hash()}:1\n"
    )
    backend.close()

    result = recover_store(root, "test-net", genesis.header.hash())
    assert result["height"] == 1


def test_corrupt_header_length_rejected(tmp_path: Path):
    root = tmp_path / "chain"
    genesis = create_genesis_block(network_id="test-net")
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    state = _initial_state()
    b = _simple_block(genesis)
    backend.append_block(b, state)
    backend.close()

    header_path = root / "headers" / "0000000001.hdr"
    header_path.write_bytes(b"short")
    with pytest.raises(StorageIOError):
        backend2 = FlatFileStorageBackend(
            chain_root=root,
            network_id="test-net",
            genesis_hash=genesis.header.hash(),
        )
        backend2.read_header(1)
        backend2.close()
