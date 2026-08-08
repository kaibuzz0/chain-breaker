"""Adversarial sync tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from chainbreaker.block import NETWORK_ID, create_genesis_block
from chainbreaker.chain import Ledger
from chainbreaker.network.messages import BlockMessage, HeaderEntry, HeadersMessage
from chainbreaker.network.sync import SyncEngine, SyncState
from chainbreaker.network.sync.block_sync import BlockSync
from chainbreaker.network.sync.header_sync import HeaderSync, header_hash
from chainbreaker.storage import FlatFileStorageBackend


@pytest.fixture
def adversarial_engine() -> Iterator[SyncEngine]:
    genesis = create_genesis_block()
    ledger = Ledger(chain=[genesis])
    with TemporaryDirectory() as tmp:
        storage = FlatFileStorageBackend(
            Path(tmp),
            network_id=NETWORK_ID,
            genesis_hash=genesis.hash,
        )
        yield SyncEngine(ledger=ledger, storage=storage)


def _headers_message(headers: list[Any], sync: HeaderSync) -> HeadersMessage:
    entries = [
        HeaderEntry(height=0, hash=header_hash(h), header_bytes=sync.encode_header(h))
        for h in headers
    ]
    return HeadersMessage(headers=entries)


def _block_message(block: Any, sync: BlockSync) -> BlockMessage:
    return BlockMessage(blocks=[{"hash": block.hash, "block_bytes": sync.encode_block(block)}])


def _build_better_chain(ledger: Ledger, count: int) -> list[Any]:
    """Build a chain extending `ledger` tip with `count` blocks."""
    blocks: list[Any] = []
    temp = Ledger(chain=list(ledger.chain))
    for _ in range(count):
        block = temp.mine_block_v2([])
        temp.add_block_v2(block)
        blocks.append(block)
    return blocks


def test_lower_work_chain_rejected(adversarial_engine: SyncEngine) -> None:
    engine = adversarial_engine
    engine.start_header_sync()
    # Same-length chain as local genesis only; no better work.
    resp = engine.handle_headers("peer", HeadersMessage(headers=[]).to_payload())
    assert resp["status"] in ("synced", "no_better_chain")


def test_invalid_header_pow_rejected(adversarial_engine: SyncEngine) -> None:
    engine = adversarial_engine
    engine.start_header_sync()
    block = engine._ledger.mine_block_v2([])
    bad = HeaderSync(engine._ledger, NETWORK_ID, 2)._decode_header(
        engine._header_sync.encode_header(block.header)
    )
    bad.nonce += 1
    msg = _headers_message([bad], engine._header_sync)
    resp = engine.handle_headers("peer", msg.to_payload())
    assert resp["status"] == "invalid"
    assert engine.state == SyncState.INVALID_DATA


def test_out_of_order_blocks_rejected(adversarial_engine: SyncEngine) -> None:
    engine = adversarial_engine
    engine.start_header_sync()
    blocks = _build_better_chain(engine._ledger, 2)
    header_msg = _headers_message([b.header for b in blocks], engine._header_sync)
    engine.handle_headers("peer", header_msg.to_payload())

    # Send second block first.
    block_msg = _block_message(blocks[1], engine._block_sync)
    resp = engine.handle_block("peer", block_msg.to_payload())
    assert resp["status"] == "invalid"


def test_engine_reset_clears_pending(adversarial_engine: SyncEngine) -> None:
    engine = adversarial_engine
    engine.start_header_sync()
    blocks = _build_better_chain(engine._ledger, 2)
    header_msg = _headers_message([b.header for b in blocks], engine._header_sync)
    engine.handle_headers("peer", header_msg.to_payload())
    engine.reset()
    assert engine.state == SyncState.IDLE
    assert engine.next_block_request() is None
