"""Tests for the relay engine."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from chainbreaker.block import NETWORK_ID, create_genesis_block
from chainbreaker.chain import Ledger
from chainbreaker.network.messages import BlockMessage, GetBlockMessage, InventoryMessage
from chainbreaker.network.relay import RelayEngine, RelayLimitPolicy
from chainbreaker.storage import FlatFileStorageBackend


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


def _block_message(engine: RelayEngine, block: Any) -> BlockMessage:
    return BlockMessage(blocks=[{"hash": block.hash, "block_bytes": engine._encode_block(block)}])


def test_on_local_block_queued(engine: RelayEngine) -> None:
    block = engine._ledger.mine_block_v2([])
    engine.on_local_block(block)
    assert block.hash in engine.build_announcements()


def test_create_inv_message(engine: RelayEngine) -> None:
    block = engine._ledger.mine_block_v2([])
    engine.on_local_block(block)
    msg = engine.create_inv_message("peer-a")
    assert msg.inv_type == "blocks"
    assert block.hash in msg.hashes


def test_handle_inv_requests_unknown_blocks(engine: RelayEngine) -> None:
    inv = InventoryMessage(inv_type="blocks", hashes=["0" * 64])
    resp = engine.handle_inv("peer-a", inv.to_payload())
    assert resp["status"] == "requested"
    assert resp["hashes"] == ["0" * 64]


def test_handle_inv_ignores_known_blocks(engine: RelayEngine) -> None:
    block = engine._ledger.mine_block_v2([])
    engine.on_local_block(block)
    inv = InventoryMessage(inv_type="blocks", hashes=[block.hash])
    resp = engine.handle_inv("peer-a", inv.to_payload())
    assert resp["status"] == "requested"
    assert resp["hashes"] == []


def test_handle_inv_rate_limits(engine: RelayEngine) -> None:
    engine = RelayEngine(ledger=engine._ledger, storage=engine._storage, limits=RelayLimitPolicy(max_inv_per_peer_per_minute=1))
    engine.handle_inv("peer-a", InventoryMessage(inv_type="blocks", hashes=["1" * 64]).to_payload(), now=0.0)
    resp = engine.handle_inv("peer-a", InventoryMessage(inv_type="blocks", hashes=["2" * 64]).to_payload(), now=0.0)
    assert resp["status"] == "rate_limited"


def test_handle_block_valid(engine: RelayEngine) -> None:
    block = engine._ledger.mine_block_v2([])
    msg = _block_message(engine, block)
    engine.handle_inv("peer-a", InventoryMessage(inv_type="blocks", hashes=[block.hash]).to_payload())
    resp = engine.handle_block("peer-a", msg.to_payload())
    assert resp["status"] == "processed"
    assert any(r["status"] == "accepted" for r in resp["results"])
    assert engine._ledger.height() == 1


def test_handle_block_duplicate(engine: RelayEngine) -> None:
    block = engine._ledger.mine_block_v2([])
    engine._seen_cache.add(block.hash, "local")
    msg = _block_message(engine, block)
    resp = engine.handle_block("peer-a", msg.to_payload())
    assert any(r["status"] == "duplicate" for r in resp["results"])


def test_handle_get_block_returns_block(engine: RelayEngine) -> None:
    block = engine._ledger.mine_block_v2([])
    engine._ledger.add_block_v2(block)
    previous_state = engine._ledger.registry_state_at(engine._ledger.height() - 1)
    engine._storage.append_block(block, previous_state=previous_state)
    msg = GetBlockMessage(hashes=[block.hash], max_total_bytes=2_000_000)
    resp = engine.handle_get_block("peer-b", msg.to_payload())
    assert resp["status"] == "sent"


def test_handle_get_block_unknown(engine: RelayEngine) -> None:
    msg = GetBlockMessage(hashes=["0" * 64], max_total_bytes=2_000_000)
    resp = engine.handle_get_block("peer-b", msg.to_payload())
    assert resp["status"] == "unknown"
