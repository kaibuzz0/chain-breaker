"""Relay-layer adversarial tests.

These tests verify that the relay engine resists inventory flooding, repeated
announcements, orphan spam, invalid block relay, request flooding, and unknown
block requests.
"""

from __future__ import annotations

from typing import Any

from chainbreaker.chain import Ledger
from chainbreaker.network.messages import InventoryMessage
from chainbreaker.network.relay import RelayEngine, RelayLimitPolicy
from tests._adversarial_block_helpers import mine_adversarial_block
from tests.network.adversarial.conftest import SimulatedPeer


def test_inventory_flooding_rate_limited(honest_peer: SimulatedPeer) -> None:
    honest_peer.relay = RelayEngine(
        ledger=honest_peer.ledger,
        storage=honest_peer.storage,
        limits=RelayLimitPolicy(max_inv_per_peer_per_minute=1),
    )
    resp1 = honest_peer.relay.handle_inv(
        "flood",
        InventoryMessage(inv_type="blocks", hashes=["1" * 64]).to_payload(),
        now=0.0,
    )
    assert resp1["status"] == "requested"
    resp2 = honest_peer.relay.handle_inv(
        "flood",
        InventoryMessage(inv_type="blocks", hashes=["2" * 64]).to_payload(),
        now=0.0,
    )
    assert resp2["status"] == "rate_limited"


def test_repeated_inventory_ignored(honest_peer: SimulatedPeer) -> None:
    inv = InventoryMessage(inv_type="blocks", hashes=["deadbeef" * 8])
    honest_peer.relay.handle_inv("peer", inv.to_payload())
    resp = honest_peer.relay.handle_inv("peer", inv.to_payload())
    assert resp["hashes"] == []


def test_orphan_spam_bounded(honest_peer: SimulatedPeer) -> None:
    honest_peer.relay = RelayEngine(
        ledger=honest_peer.ledger,
        storage=honest_peer.storage,
        limits=RelayLimitPolicy(max_orphan_blocks=4),
    )
    for i in range(8):
        temp = Ledger(chain=list(honest_peer.ledger.chain))
        block = mine_adversarial_block(temp, [{"id": f"tx-{i}"}])
        honest_peer.relay.add_orphan(block, "peer-a", now=0.0)
    assert len(honest_peer.relay._orphans) <= 4


def test_invalid_block_relay_rejected(honest_peer: SimulatedPeer) -> None:
    block = honest_peer.ledger.mine_block_v2([])
    # Break validity without changing the header hash.
    block.transactions.append({"id": "duplicate"})
    block.transactions.append({"id": "duplicate"})
    resp = honest_peer.relay.handle_block(
        "peer",
        honest_peer.build_block_message(block).to_payload(),
        now=0.0,
    )
    assert any(r["status"] == "invalid" for r in resp["results"])
    assert block.hash not in honest_peer.relay._local_blocks_to_announce


def test_get_block_request_size_rate_limited(honest_peer: SimulatedPeer) -> None:
    # A GET_BLOCK request for more hashes than max_blocks_response is
    # rate-limited, preventing request amplification.
    honest_peer.relay = RelayEngine(
        ledger=honest_peer.ledger,
        storage=honest_peer.storage,
        limits=RelayLimitPolicy(max_blocks_response=2),
    )
    msg = honest_peer.build_get_block_message([f"{i:064x}" for i in range(10)])
    resp = honest_peer.relay.handle_get_block("peer", msg.to_payload())
    assert resp["status"] == "rate_limited"


def test_unknown_block_request_safe(honest_peer: SimulatedPeer) -> None:
    msg = honest_peer.build_get_block_message(["0" * 64])
    resp = honest_peer.relay.handle_get_block("peer", msg.to_payload())
    assert resp["status"] == "unknown"


def test_relay_does_not_forward_unvalidated_blocks(honest_peer: SimulatedPeer, adversarial_peer: SimulatedPeer) -> None:
    # Adversary sends an invalid block through the relay path. Relay validates
    # it with consensus and must not accept or forward it.
    block = adversarial_peer.ledger.mine_block_v2([])
    block.transactions.append({"id": "dup"})
    block.transactions.append({"id": "dup"})
    resp = honest_peer.relay.handle_block(
        "adversarial",
        honest_peer.build_block_message(block).to_payload(),
        now=0.0,
    )
    assert any(r["status"] == "invalid" for r in resp["results"])
    assert block.hash not in honest_peer.relay._local_blocks_to_announce


def _build_better_chain(base_ledger: Ledger, count: int) -> list[Any]:
    blocks: list[Any] = []
    temp = Ledger(chain=list(base_ledger.chain))
    for _ in range(count):
        block = temp.mine_block_v2([])
        temp.add_block_v2(block)
        blocks.append(block)
    return blocks


def test_orphan_connect_attempt_does_not_bypass_validation(honest_peer: SimulatedPeer, adversarial_peer: SimulatedPeer) -> None:
    # Adversary sends an orphan, then the parent. The relay stores the orphan
    # but does not accept the child without consensus validation.
    parent, child = _build_better_chain(adversarial_peer.ledger, 2)
    honest_peer.relay.add_orphan(child, "peer-a", now=0.0)
    assert child.hash in honest_peer.relay._orphans

    # The parent is valid for the honest ledger and is accepted.
    resp = honest_peer.relay.handle_block(
        "peer-a",
        honest_peer.build_block_message(parent).to_payload(),
        now=0.0,
    )
    assert any(r["status"] == "accepted" for r in resp["results"])

    # The orphan may be removed from the pool when its parent connects, but it
    # is never accepted or forwarded without its own consensus validation.
    assert child.hash not in honest_peer.relay._local_blocks_to_announce
    assert child.hash not in honest_peer.relay._seen_cache._cache
