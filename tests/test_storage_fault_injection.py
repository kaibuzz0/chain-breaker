"""Fault-injection tests for the storage backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block
from chainbreaker.registry_state import RegistryState
from chainbreaker.storage import FlatFileStorageBackend
from chainbreaker.storage.failpoint import FailpointController


def _simple_block(prev: BlockV2) -> BlockV2:
    header = BlockHeaderV2(
        version=2,
        prev_hash=prev.header.hash(),
        merkle_root="0" * 64,
        registry_root="0" * 64,
        timestamp=prev.header.timestamp + 600,
        target=2 ** 220,
        nonce=0,
    )
    b = BlockV2(header=header, transactions=[])
    b.header.mine(max_iterations=100_000)
    return b


def _initial_state() -> RegistryState:
    return RegistryState.genesis(
        governance_keys=["0" * 64, "1" * 64],
        threshold=1,
    )


def test_failpoint_before_begin_blocks_commit(tmp_path: Path):
    root = tmp_path / "chain"
    genesis = create_genesis_block(network_id="test-net")
    fail = FailpointController()
    fail.arm("before_begin", lambda: (_ for _ in ()).throw(RuntimeError("crash before begin")))

    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
        failpoint=fail.fire,
    )
    with pytest.raises(RuntimeError, match="crash before begin"):
        backend.append_block(_simple_block(genesis), _initial_state())
    assert backend.get_tip()["height"] == 0
    backend.close()


def test_failpoint_after_begin_recoverable(tmp_path: Path):
    root = tmp_path / "chain"
    genesis = create_genesis_block(network_id="test-net")
    fail = FailpointController()
    fail.arm("after_begin", lambda: (_ for _ in ()).throw(RuntimeError("crash after begin")))

    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
        failpoint=fail.fire,
    )
    with pytest.raises(RuntimeError, match="crash after begin"):
        backend.append_block(_simple_block(genesis), _initial_state())
    backend.close()

    # Recovery should roll back the incomplete BEGIN and restore tip to genesis.
    from chainbreaker.storage.recovery import recover_store

    result = recover_store(root, "test-net", genesis.header.hash())
    assert result["height"] == 0
    assert result["block_hash"] == genesis.header.hash()
