"""Lightweight storage performance baseline tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block
from chainbreaker.registry_state import RegistryState
from chainbreaker.storage import FlatFileStorageBackend, recover_store


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


@pytest.mark.slow
@pytest.mark.timeout(120)
def test_append_100_blocks_latency_baseline(tmp_path: Path):
    import time

    genesis = create_genesis_block(network_id="test-net")
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash=genesis.header.hash(),
    )
    state = _initial_state()
    prev = genesis
    start = time.perf_counter()
    for _ in range(100):
        b = _simple_block(prev)
        state = backend.append_block(b, state)
        prev = b
    elapsed = time.perf_counter() - start
    backend.close()
    print(f"100 appends: {elapsed:.3f}s ({elapsed / 100 * 1000:.2f} ms/append)")
    assert backend.get_tip()["height"] == 100

    rstart = time.perf_counter()
    result = recover_store(root, "test-net", genesis.header.hash())
    relapsed = time.perf_counter() - rstart
    print(f"100-block recovery: {relapsed:.3f}s")
    assert result["height"] == 100
