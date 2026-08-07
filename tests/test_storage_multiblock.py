"""Multi-block crash and randomized fault tests."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block
from chainbreaker.registry_state import RegistryState
from chainbreaker.storage import FlatFileStorageBackend, recover_store
from chainbreaker.storage.failpoint import FailpointController


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


def _append_chain(backend: FlatFileStorageBackend, genesis: BlockV2, count: int) -> tuple[list[BlockV2], RegistryState]:
    state = _initial_state()
    blocks: list[BlockV2] = []
    prev = genesis
    for _ in range(count):
        b = _simple_block(prev)
        state = backend.append_block(b, state)
        blocks.append(b)
        prev = b
    return blocks, state


def test_100_block_chain_recovery(tmp_path: Path):
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    try:
        _append_chain(backend, genesis, 100)
        assert backend.get_tip()["height"] == 100
    finally:
        backend.close()

    result = recover_store(root, "test-net", genesis.header.hash())
    assert result["height"] == 100


@pytest.mark.parametrize("seed", list(range(5)))
def test_randomized_fault_sequence(tmp_path: Path, seed: int):
    rng = random.Random(seed)
    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    state = _initial_state()
    prev = genesis
    target_height = 20
    for height in range(1, target_height + 1):
        b = _simple_block(prev, nonce=rng.randint(0, 1_000_000))
        fail = FailpointController()
        crash_after = rng.choice([
            None,
            "before_begin",
            "after_publish",
            "before_head_update",
            "after_head_update",
        ])
        if crash_after:
            fail.arm(crash_after, lambda: (_ for _ in ()).throw(RuntimeError("crash")))
        backend = FlatFileStorageBackend(
            chain_root=root,
            network_id="test-net",
            genesis_hash=genesis.header.hash(),
            failpoint=fail.fire,
        )
        try:
            state = backend.append_block(b, state)
            height = backend.get_tip()["height"]
        except RuntimeError:
            pass
        finally:
            backend.close()

        result = recover_store(root, "test-net", genesis.header.hash())
        recovered = result["height"]
        assert 0 <= recovered <= height

        backend2 = FlatFileStorageBackend(
            chain_root=root,
            network_id="test-net",
            genesis_hash=genesis.header.hash(),
        )
        try:
            tip = backend2.get_tip()
            assert tip["height"] == recovered
            if recovered > 0:
                prev = backend2.read_block(recovered)
                state = _initial_state()
            else:
                prev = genesis
        finally:
            backend2.close()
