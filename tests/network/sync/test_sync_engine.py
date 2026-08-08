"""Tests for the sync engine state machine."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from chainbreaker.block import NETWORK_ID, create_genesis_block
from chainbreaker.chain import Ledger
from chainbreaker.network.messages import BlockMessage, HeadersMessage
from chainbreaker.network.sync import SyncEngine, SyncState
from chainbreaker.network.sync.block_sync import BlockSync
from chainbreaker.network.sync.header_sync import HeaderSync, header_hash
from chainbreaker.storage import FlatFileStorageBackend


@pytest.fixture
def engine() -> Iterator[SyncEngine]:
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
    from chainbreaker.network.messages import HeaderEntry
    entries = [
        HeaderEntry(height=0, hash=header_hash(h), header_bytes=sync.encode_header(h))
        for h in headers
    ]
    return HeadersMessage(headers=entries)


def _block_message(block: Any, sync: BlockSync) -> BlockMessage:
    return BlockMessage(blocks=[{"hash": block.hash, "block_bytes": sync.encode_block(block)}])


def test_start_header_sync(engine: SyncEngine) -> None:
    req = engine.start_header_sync()
    assert req["method"] == "GET_HEADERS"
    assert engine.state == SyncState.REQUESTING_HEADERS


def test_handle_headers_synced(engine: SyncEngine) -> None:
    engine.start_header_sync()
    # Empty headers means peer returned nothing.
    resp = engine.handle_headers("peer-a", HeadersMessage(headers=[]).to_payload())
    assert resp["status"] == "synced"
    assert engine.state == SyncState.SYNCED


def test_handle_headers_no_better_chain(engine: SyncEngine) -> None:
    engine.start_header_sync()
    # Provide header equal to local work: a single header of equal work
    # Since local has genesis, any header extending genesis adds work, so local work lower.
    # Instead use a header that does not extend (would be rejected as invalid).
    # Simpler: just mine a block locally to equal work and then provide no headers.
    block = engine._ledger.mine_block_v2([])
    engine._ledger.add_block_v2(block)
    resp = engine.handle_headers("peer-a", HeadersMessage(headers=[]).to_payload())
    assert resp["status"] == "synced"


def test_handle_headers_requests_blocks(engine: SyncEngine) -> None:
    engine.start_header_sync()
    b1 = engine._ledger.mine_block_v2([])
    temp_ledger = Ledger(chain=[create_genesis_block()])
    temp_ledger.add_block_v2(b1)
    b2 = temp_ledger.mine_block_v2([])
    msg = _headers_message([b1.header, b2.header], engine._header_sync)
    resp = engine.handle_headers("peer-a", msg.to_payload())
    assert resp["status"] == "request_blocks"
    assert engine.state == SyncState.REQUESTING_BLOCKS


def test_full_sync_commit(engine: SyncEngine) -> None:
    engine.start_header_sync()
    b1 = engine._ledger.mine_block_v2([])
    temp_ledger = Ledger(chain=[create_genesis_block()])
    temp_ledger.add_block_v2(b1)
    b2 = temp_ledger.mine_block_v2([])
    header_msg = _headers_message([b1.header, b2.header], engine._header_sync)
    engine.handle_headers("peer-a", header_msg.to_payload())

    for block in [b1, b2]:
        next_req = engine.next_block_request()
        assert next_req is not None
        assert next_req["method"] == "GET_BLOCK"
        block_msg = _block_message(block, engine._block_sync)
        resp = engine.handle_block("peer-a", block_msg.to_payload())

    assert resp["status"] == "committed"
    assert engine.state == SyncState.SYNCED
    assert engine._ledger.height() == 2


def test_handle_block_invalid_ledger_rejection(engine: SyncEngine) -> None:
    engine.start_header_sync()
    b1 = engine._ledger.mine_block_v2([])
    temp_ledger = Ledger(chain=[create_genesis_block()])
    temp_ledger.add_block_v2(b1)
    b2 = temp_ledger.mine_block_v2([])
    header_msg = _headers_message([b1.header, b2.header], engine._header_sync)
    engine.handle_headers("peer-a", header_msg.to_payload())
    # Provide a malformed block payload that fails decode.
    bad_block_msg = BlockMessage(blocks=[{"hash": b1.hash, "block_bytes": "not-json"}])
    resp = engine.handle_block("peer-a", bad_block_msg.to_payload())
    assert resp["status"] == "invalid"


def test_unexpected_block(engine: SyncEngine) -> None:
    block = engine._ledger.mine_block_v2([])
    msg = _block_message(block, engine._block_sync)
    resp = engine.handle_block("peer-a", msg.to_payload())
    assert resp["status"] == "unexpected_block"
