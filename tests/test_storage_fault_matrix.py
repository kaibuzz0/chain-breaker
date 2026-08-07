"""Exhaustive commit-step fault matrix for durable storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block
from chainbreaker.registry_state import RegistryState
from chainbreaker.storage import FlatFileStorageBackend, recover_store
from chainbreaker.storage.failpoint import FailpointController

FAILPOINTS = [
    "before_begin",
    "after_begin",
    "before_header_stage",
    "after_header_stage",
    "after_header_staged_record",
    "before_block_stage",
    "after_block_stage",
    "after_block_staged_record",
    "before_registry_stage",
    "after_registry_stage",
    "after_registry_staged_record",
    "before_publish",
    "during_header_rename",
    "after_header_publish",
    "during_block_rename",
    "after_block_publish",
    "after_snapshot_publish",
    "before_index_stage",
    "after_index_stage",
    "after_publish",
    "before_fsync",
    "after_fsync",
    "before_commit",
    "after_commit",
    "before_head_update",
    "after_head_update",
    "before_dir_sync",
    "after_dir_sync",
]


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


def _append_one(root: Path, failpoint_name: str, genesis: BlockV2) -> tuple[int, RegistryState]:
    fail = FailpointController()
    fail.arm(failpoint_name, lambda: (_ for _ in ()).throw(RuntimeError("failpoint")))
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
        failpoint=fail.fire,
    )
    state = _initial_state()
    b = _simple_block(genesis)
    try:
        state = backend.append_block(b, state)
        committed_height = backend.get_tip()["height"]
    except RuntimeError:
        committed_height = backend.get_tip()["height"]
    finally:
        backend.close()
    return committed_height, state


@pytest.mark.parametrize("failpoint", FAILPOINTS)
def test_fault_matrix_restart(tmp_path: Path, failpoint: str):
    """Crash at each commit step and assert recovery yields a valid state."""
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"

    committed_height, _state = _append_one(root, failpoint, genesis)

    # Recover
    result = recover_store(root, "test-net", genesis.header.hash())
    final_height = result["height"]

    # Valid states after crash: previous genesis (0) or committed block (1)
    assert final_height in (0, 1)

    # If height is 1, we must be able to continue appending.
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        tip = backend.get_tip()
        assert tip["height"] == final_height
        if final_height == 0:
            assert tip["block_hash"] == genesis.header.hash()
        # Attempt next append succeeds and leaves store in valid state.
        next_block = _simple_block(genesis)
        state = _initial_state()
        if final_height == 1:
            # If we committed block 1, next block must use it as prev.
            existing_block = backend.read_block(1)
            next_block = _simple_block(existing_block)
            # state would normally be from previous commit; here just use genesis state as simple test
        backend.append_block(next_block, state)
        assert backend.get_tip()["height"] == final_height + 1
    finally:
        backend.close()
