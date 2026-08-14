"""Adversarial relay tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from chainbreaker.block import NETWORK_ID, create_genesis_block
from chainbreaker.chain import Ledger
from chainbreaker.network.messages import BlockMessage, InventoryMessage
from chainbreaker.network.relay import RelayEngine, RelayLimitPolicy
from chainbreaker.storage import FlatFileStorageBackend
from tests._adversarial_block_helpers import mine_adversarial_block


@pytest.fixture
def engine() -> Iterator[RelayEngine]:
    genesis = create_genesis_block()
    ledger = Ledger(chain=[genesis])
    with TemporaryDirectory() as tmp:
        storage = FlatFileStorageBackend(
            Path(tmp),
            network_id=NETWORK_ID,
            genesis_hash=genesis.hash,
        )
        yield RelayEngine(ledger=ledger, storage=storage)


def test_oversized_inventory_truncated(engine: RelayEngine) -> None:
    hashes = [f"{i:064x}" for i in range(300)]
    inv = InventoryMessage(inv_type="blocks", hashes=hashes)
    resp = engine.handle_inv("peer-a", inv.to_payload())
    assert resp["status"] == "requested"
    assert len(resp["hashes"]) <= engine._limits.max_inv_items


def test_invalid_block_hash_mismatch(engine: RelayEngine) -> None:
    block = engine._ledger.mine_block_v2([])
    msg = BlockMessage(blocks=[{"hash": "0" * 64, "block_bytes": engine._encode_block(block)}])
    resp = engine.handle_block("peer-a", msg.to_payload())
    assert any(r["status"] == "invalid" for r in resp["results"])


def test_repeated_inv_suppressed(engine: RelayEngine) -> None:
    inv = InventoryMessage(inv_type="blocks", hashes=["a" * 64])
    engine.handle_inv("peer-a", inv.to_payload())
    resp = engine.handle_inv("peer-a", inv.to_payload())
    assert resp["hashes"] == []


def test_orphan_pool_bound(engine: RelayEngine) -> None:
    engine = RelayEngine(ledger=engine._ledger, storage=engine._storage, limits=RelayLimitPolicy(max_orphan_blocks=2))
    for i in range(3):
        temp = Ledger(chain=list(engine._ledger.chain))
        block = mine_adversarial_block(temp, [{"id": f"tx-{i}"}])
        engine.add_orphan(block, "peer-a", now=0.0)
    assert len(engine._orphans) == 2


def test_inventory_flood_rate_limited(engine: RelayEngine) -> None:
    engine = RelayEngine(ledger=engine._ledger, storage=engine._storage, limits=RelayLimitPolicy(max_inv_per_peer_per_minute=1))
    resp1 = engine.handle_inv("peer-a", InventoryMessage(inv_type="blocks", hashes=["1" * 64]).to_payload(), now=0.0)
    assert resp1["status"] == "requested"
    resp2 = engine.handle_inv("peer-a", InventoryMessage(inv_type="blocks", hashes=["2" * 64]).to_payload(), now=0.0)
    assert resp2["status"] == "rate_limited"
