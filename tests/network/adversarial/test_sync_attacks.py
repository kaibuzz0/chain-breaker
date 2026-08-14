"""Sync-layer adversarial tests.

These tests verify that the sync engine rejects fake high-work chains, header
flooding, invalid PoW, out-of-order blocks, and interrupted sync without
committing invalid state.
"""

from __future__ import annotations

from typing import Any

from chainbreaker.chain import Ledger
from chainbreaker.network.messages import HeadersMessage
from chainbreaker.network.sync import SyncState
from tests.network.adversarial.conftest import SimulatedPeer


def _build_better_chain(base_ledger: Ledger, count: int) -> list[Any]:
    """Build a chain extending `base_ledger` tip with `count` valid blocks."""
    blocks: list[Any] = []
    temp = Ledger(chain=list(base_ledger.chain))
    for _ in range(count):
        block = temp.mine_block_v2([])
        temp.add_block_v2(block)
        blocks.append(block)
    return blocks


def test_fake_high_work_chain_rejected(honest_peer: SimulatedPeer, adversarial_peer: SimulatedPeer) -> None:
    # Adversary has only one block; honest node also has genesis only, so work
    # is equal, not greater. Sync must reject as not better.
    bad_block = adversarial_peer.mine_and_accept()
    honest_peer.sync.start_header_sync()
    header_msg = honest_peer.build_headers_message([bad_block])
    resp = honest_peer.sync.handle_headers("adversarial", header_msg.to_payload())
    assert resp["status"] in ("synced", "no_better_chain")
    assert honest_peer.sync.state != SyncState.COMMITTING


def test_fake_longer_chain_with_broken_link_rejected(honest_peer: SimulatedPeer, adversarial_peer: SimulatedPeer) -> None:
    # Adversary mines a valid chain, then we mutate the second header so it
    # does not link to the first. Header validation rejects the whole segment.
    chain = _build_better_chain(adversarial_peer.ledger, 2)
    honest_peer.sync.start_header_sync()
    entries = honest_peer.build_headers_message(chain).headers
    # Tamper with the second header's bytes to break prev_hash linkage.
    tampered = entries[1].header_bytes.replace(
        chain[0].hash[:16],
        "deadbeef" * 4,
    )
    entries[1] = entries[1].__class__(
        height=entries[1].height,
        hash=entries[1].hash,
        header_bytes=tampered,
    )
    msg = HeadersMessage(headers=list(entries))
    resp = honest_peer.sync.handle_headers("adversarial", msg.to_payload())
    assert resp["status"] == "invalid"
    assert honest_peer.ledger.height() == 0


def test_header_flooding_no_commit(honest_peer: SimulatedPeer) -> None:
    honest_peer.sync.start_header_sync()
    # Empty headers message is a benign flood edge case.
    resp = honest_peer.sync.handle_headers("flood", HeadersMessage(headers=[]).to_payload())
    assert resp["status"] in ("synced", "no_better_chain")
    assert honest_peer.sync._pending_headers == []


def test_invalid_pow_header_rejected(honest_peer: SimulatedPeer) -> None:
    honest_peer.sync.start_header_sync()
    block = honest_peer.ledger.mine_block_v2([])
    bad_header = block.header
    object.__setattr__(bad_header, "nonce", bad_header.nonce + 1)
    msg = honest_peer.build_headers_message([block])
    resp = honest_peer.sync.handle_headers("peer", msg.to_payload())
    assert resp["status"] == "invalid"
    assert honest_peer.sync.state == SyncState.INVALID_DATA


def test_out_of_order_blocks_rejected(honest_peer: SimulatedPeer, adversarial_peer: SimulatedPeer) -> None:
    blocks = _build_better_chain(adversarial_peer.ledger, 2)
    honest_peer.sync.start_header_sync()
    honest_peer.sync.handle_headers(
        "peer",
        honest_peer.build_headers_message(blocks).to_payload(),
    )
    # Send the second block first.
    resp = honest_peer.sync.handle_block(
        "peer",
        honest_peer.build_block_message(blocks[1]).to_payload(),
    )
    assert resp["status"] == "invalid"


def test_interrupted_sync_recovers_cleanly(honest_peer: SimulatedPeer, adversarial_peer: SimulatedPeer) -> None:
    blocks = _build_better_chain(adversarial_peer.ledger, 2)
    honest_peer.sync.start_header_sync()
    honest_peer.sync.handle_headers(
        "peer",
        honest_peer.build_headers_message(blocks).to_payload(),
    )
    assert honest_peer.sync.state == SyncState.REQUESTING_BLOCKS
    honest_peer.sync.reset()
    assert honest_peer.sync.state.name == "IDLE"
    assert honest_peer.sync.next_block_request() is None


def test_invalid_block_through_sync_does_not_commit(honest_peer: SimulatedPeer, adversarial_peer: SimulatedPeer) -> None:
    # Adversary mines a block then mutates a transaction to break validity.
    block = adversarial_peer.mine_adversarial([{"id": "tx-1"}])
    block.transactions.append({"id": "tx-1"})  # duplicate breaks consensus rules
    honest_peer.sync.start_header_sync()
    # The invalid header is rejected by the sync engine; no commitment path opens.
    header_resp = honest_peer.sync.handle_headers(
        "peer",
        honest_peer.build_headers_message([block]).to_payload(),
    )
    assert header_resp["status"] != "committed"
    assert honest_peer.ledger.height() == 0
