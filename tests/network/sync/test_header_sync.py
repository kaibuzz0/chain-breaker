"""Tests for header synchronization."""

from __future__ import annotations

from typing import Any

import pytest

from chainbreaker.block import create_genesis_block
from chainbreaker.chain import Ledger
from chainbreaker.network.messages import HeaderEntry, HeadersMessage
from chainbreaker.network.sync import HeaderSync, SyncInvalidDataError
from chainbreaker.network.sync.header_sync import header_hash


@pytest.fixture
def fresh_ledger() -> Ledger:
    genesis = create_genesis_block()
    return Ledger(chain=[genesis])


def _make_headers_message(headers: list[Any], header_sync: HeaderSync) -> HeadersMessage:
    entries = [
        HeaderEntry(height=0, hash=header_hash(h), header_bytes=header_sync.encode_header(h))
        for h in headers
    ]
    return HeadersMessage(headers=entries)


def test_build_locator(fresh_ledger: Ledger) -> None:
    sync = HeaderSync(fresh_ledger, network_id="chainbreaker-scripture-v2", protocol_version=2)
    loc = sync.build_locator()
    assert loc[-1] == fresh_ledger.genesis_hash()
    assert len(loc) <= 32


def test_create_get_headers(fresh_ledger: Ledger) -> None:
    sync = HeaderSync(fresh_ledger, network_id="chainbreaker-scripture-v2", protocol_version=2)
    msg = sync.create_get_headers()
    assert msg.start_hashes[-1] == fresh_ledger.genesis_hash()
    assert msg.max_count > 0


def test_parse_valid_headers(fresh_ledger: Ledger) -> None:
    sync = HeaderSync(fresh_ledger, network_id="chainbreaker-scripture-v2", protocol_version=2)
    next_block = fresh_ledger.mine_block_v2([])
    msg = _make_headers_message([next_block.header], sync)
    headers = sync.parse_headers_message(msg)
    assert len(headers) == 1
    assert headers[0].prev_hash == fresh_ledger.last_block.hash


def test_reject_wrong_prev_hash(fresh_ledger: Ledger) -> None:
    sync = HeaderSync(fresh_ledger, network_id="chainbreaker-scripture-v2", protocol_version=2)
    next_block = fresh_ledger.mine_block_v2([])
    # Corrupt prev_hash by mutating the header after encoding? Build header with bad prev.
    bad = HeaderSync(fresh_ledger, "", 2)._decode_header(sync.encode_header(next_block.header))
    bad.prev_hash = "0" * 64
    msg = _make_headers_message([bad], sync)
    with pytest.raises(SyncInvalidDataError):
        sync.parse_headers_message(msg)


def test_reject_bad_pow(fresh_ledger: Ledger) -> None:
    sync = HeaderSync(fresh_ledger, network_id="chainbreaker-scripture-v2", protocol_version=2)
    next_block = fresh_ledger.mine_block_v2([])
    bad = sync._decode_header(sync.encode_header(next_block.header))
    bad.nonce += 1
    msg = _make_headers_message([bad], sync)
    with pytest.raises(SyncInvalidDataError):
        sync.parse_headers_message(msg)
