"""Adversarial corruption tests for storage components."""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block
from chainbreaker.crypto import HashEngine
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


def _append_chain(backend: FlatFileStorageBackend, genesis: BlockV2, count: int) -> RegistryState:
    state = _initial_state()
    prev = genesis
    for _ in range(count):
        b = _simple_block(prev)
        state = backend.append_block(b, state)
        prev = b
    return state


def test_journal_truncated_final_record(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        _append_chain(backend, genesis, 2)
    finally:
        backend.close()

    journal_path = root / "journal"
    data = journal_path.read_bytes()
    journal_path.write_bytes(data[:-8])

    result = recover_store(root, "test-net", genesis.header.hash())
    assert result["height"] in (0, 1, 2)


def test_journal_corrupted_checksum(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        _append_chain(backend, genesis, 2)
    finally:
        backend.close()

    journal_path = root / "journal"
    data = bytearray(journal_path.read_bytes())
    # Flip a bit inside the first record checksum at the end.
    data[-1] ^= 0xFF
    journal_path.write_bytes(data)

    result = recover_store(root, "test-net", genesis.header.hash())
    # Recovery may ignore the corrupt trailing record and find an earlier valid commit.
    assert result["height"] in (0, 1, 2)


def test_head_missing(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        _append_chain(backend, genesis, 3)
    finally:
        backend.close()
    (root / "HEAD").unlink()

    result = recover_store(root, "test-net", genesis.header.hash())
    # Without HEAD, recovery falls back to journal commits or zero.
    assert 0 <= result["height"] <= 3


def test_head_ahead_of_durable_data(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        _append_chain(backend, genesis, 3)
    finally:
        backend.close()
    # Corrupt HEAD to a future height without matching block.
    (root / "HEAD").write_text(
        f"00000000000000000999:{genesis.header.hash()}:test-net:{genesis.header.hash()}:1\n"
    )
    result = recover_store(root, "test-net", genesis.header.hash())
    assert result["height"] <= 3


def test_header_wrong_length(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        _append_chain(backend, genesis, 3)
    finally:
        backend.close()

    header_path = root / "headers" / "0000000002.hdr"
    header_path.write_bytes(b"x" * 148)
    result = recover_store(root, "test-net", genesis.header.hash())
    assert result["height"] <= 1


def test_snapshot_inconsistent_rejected(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        state = _append_chain(backend, genesis, 3)
        backend.write_snapshot(3, state)
    finally:
        backend.close()

    snapshot_path = root / "registry" / "snapshots" / "0000000003.state"
    data = snapshot_path.read_bytes()
    # Corrupt the snapshot body so state_hash meta check fails on load.
    snapshot_path.write_bytes(data[:-1])

    backend2 = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        with pytest.raises(StorageIOError):
            backend2.read_snapshot(3)
    finally:
        backend2.close()


def test_index_rebuilds_after_corruption(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        _append_chain(backend, genesis, 3)
    finally:
        backend.close()

    (root / "indexes" / "height_to_hash.json").write_bytes(b"garbage")
    result = recover_store(root, "test-net", genesis.header.hash())
    assert result["height"] == 3
    assert result["rebuilt_indexes"] == ["1", "2", "3"]


def test_archive_object_hash_mismatch_rejected(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        data = b"hello archive"
        content_hash = HashEngine.hash_single_hex(data)
        backend.put_archive_object(content_hash, data)
        # Read back
        assert backend.get_archive_object(content_hash) == data
        # Corrupt stored file
        path = root / "archive" / "objects" / content_hash[:2] / content_hash[2:4] / content_hash
        path.write_bytes(b"tampered")
        with pytest.raises(StorageIOError):
            backend.get_archive_object(content_hash)
    finally:
        backend.close()
