"""Tests for block synchronization."""

from __future__ import annotations

from typing import Any

import pytest

from chainbreaker.block import create_genesis_block
from chainbreaker.chain import Ledger
from chainbreaker.network.messages import BlockMessage
from chainbreaker.network.sync import BlockSync, SyncInvalidDataError


@pytest.fixture
def fresh_ledger() -> Ledger:
    genesis = create_genesis_block()
    return Ledger(chain=[genesis])


def _block_message(block: Any) -> BlockMessage:
    sync = BlockSync(Ledger(chain=[create_genesis_block()]))
    return BlockMessage(blocks=[{"hash": block.hash, "block_bytes": sync.encode_block(block)}])


def test_parse_valid_block(fresh_ledger: Ledger) -> None:
    sync = BlockSync(fresh_ledger)
    block = fresh_ledger.mine_block_v2([])
    msg = _block_message(block)
    parsed = sync.parse_block_message(msg, expected_height=1, expected_prev_hash=fresh_ledger.last_block.hash)
    assert parsed.hash == block.hash


def test_reject_wrong_prev_hash(fresh_ledger: Ledger) -> None:
    sync = BlockSync(fresh_ledger)
    block = fresh_ledger.mine_block_v2([])
    with pytest.raises(SyncInvalidDataError):
        sync.parse_block_message(_block_message(block), expected_height=1, expected_prev_hash="0" * 64)


def test_reject_multiple_blocks(fresh_ledger: Ledger) -> None:
    sync = BlockSync(fresh_ledger)
    block = fresh_ledger.mine_block_v2([])
    encoded = sync.encode_block(block)
    msg = BlockMessage(blocks=[
        {"hash": block.hash, "block_bytes": encoded},
        {"hash": block.hash, "block_bytes": encoded},
    ])
    with pytest.raises(SyncInvalidDataError):
        sync.parse_block_message(msg, expected_height=1, expected_prev_hash=fresh_ledger.last_block.hash)
