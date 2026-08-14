"""Combined-stack adversarial tests.

These tests verify that a malicious peer traversing handshake, discovery,
gossip, sync, and relay cannot corrupt state, bypass consensus, or exhaust
resources.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from chainbreaker.network import (
    HELLO,
    HELLO_ACK,
    NET_PROTOCOL_VERSION,
    NETWORK_ID,
    PEX,
    NetworkEnvelope,
    parse_envelope,
    serialize_envelope,
)
from chainbreaker.network.discovery.errors import PeerTableFullError
from chainbreaker.network.discovery.peer_table import PeerRecord, PeerSource
from chainbreaker.network.messages import HelloMessage, InventoryMessage
from chainbreaker.network.transport import (
    TransportValidationError,
    create_memory_transport_pair,
)
from tests._adversarial_block_helpers import mine_adversarial_block
from tests.network.adversarial.conftest import SimulatedPeer

LOCAL_FEATURES = frozenset({"headers", "blocks", "relay"})




def _hello_payload(
    network_id: str = NETWORK_ID,
    genesis_hash: str | None = None,
    protocol_version: int = NET_PROTOCOL_VERSION,
) -> bytes:
    from chainbreaker.block import create_genesis_block
    return HelloMessage(
        protocol_version=protocol_version,
        network_id=network_id,
        genesis_hash=genesis_hash or create_genesis_block().hash,
        best_height=0,
        best_chain_work="0" * 64,
        feature_bits=sorted(LOCAL_FEATURES),
        node_limits={},
    ).to_payload()


def _hello_envelope(
    network_id: str = NETWORK_ID,
    genesis_hash: str | None = None,
    protocol_version: int = NET_PROTOCOL_VERSION,
) -> NetworkEnvelope:
    return parse_envelope(serialize_envelope(
        HELLO,
        payload=_hello_payload(network_id, genesis_hash, protocol_version),
    ))


def _ack_envelope(ok: bool = True, reason: str = "") -> NetworkEnvelope:
    import json
    return parse_envelope(serialize_envelope(
        HELLO_ACK,
        payload=json.dumps({"ok": ok, "reason": reason}, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    ))


async def _run_full_stack_attack(honest_peer: SimulatedPeer) -> None:
    manager = honest_peer.connection_manager
    peer_key = "attacker"

    # 1. Handshake attack: wrong network_id is rejected and recorded.
    for i in range(3):
        a, b = create_memory_transport_pair()
        task = asyncio.create_task(manager.register_inbound(f"in-{i}", a, peer_key))
        await b.send(_hello_envelope(network_id="wrong-net"))
        await b.receive()
        with contextlib.suppress(TransportValidationError):
            await task
    assert manager.is_banned(peer_key)

    # 2. Discovery attack: try to flood the peer table from the banned peer.
    table = honest_peer.discovery.peer_table
    for j in range(32):
        with contextlib.suppress(PeerTableFullError):
            table.add(
                PeerRecord(
                    peer_id=f"{peer_key}-{j}",
                    host="127.0.0.1",
                    port=40000 + j,
                    source=PeerSource.PEX,
                    score=0,
                )
            )
    assert table.size <= table._max_entries

    # 3. Gossip attack: duplicate/storm messages are suppressed/rate-limited.
    from chainbreaker.network.gossip import GossipEngine, GossipRateLimitError
    gossip = GossipEngine()
    env = NetworkEnvelope(
        message_type=PEX,
        flags=0,
        payload=b'{"peers":[],"ttl":3,"hop_count":0}',
    )
    gossip.receive(env, peer_key)
    with pytest.raises(GossipRateLimitError):
        for _ in range(20):
            gossip.receive(env, peer_key)

    # 4. Sync attack: invalid header chain rejected.
    honest_peer.sync.start_header_sync()
    invalid_block = honest_peer.ledger.mine_block_v2([])
    object.__setattr__(invalid_block.header, "nonce", invalid_block.header.nonce + 1)
    header_msg = honest_peer.build_headers_message([invalid_block])
    sync_resp = honest_peer.sync.handle_headers(peer_key, header_msg.to_payload())
    assert sync_resp["status"] == "invalid"

    # 5. Relay attack: invalid block inventory rate limited.
    inv = InventoryMessage(inv_type="blocks", hashes=[invalid_block.hash])
    relay_resp = honest_peer.relay.handle_inv(peer_key, inv.to_payload(), now=0.0)
    assert relay_resp["status"] in ("requested", "rate_limited")

    # Final state must remain consistent and bounded.
    assert manager.available_slots >= 0
    assert table.size <= table._max_entries
    assert honest_peer.ledger.height() == 0


def test_malicious_peer_traverses_all_layers(honest_peer: SimulatedPeer) -> None:
    asyncio.run(_run_full_stack_attack(honest_peer))


async def _run_reconnect_inventory_orphan_storm(honest_peer: SimulatedPeer, adversarial_peer: SimulatedPeer) -> None:
    manager = honest_peer.connection_manager
    table = honest_peer.discovery.peer_table

    # Reconnect storm: many inbound attempts, all rejected after capacity.
    for i in range(32):
        if manager.available_slots == 0:
            break
        a, b = create_memory_transport_pair()
        task = asyncio.create_task(
            manager.register_inbound(f"storm-{i}", a, f"storm-{i}"),
        )
        await b.send(_hello_envelope())
        await b.receive()
        with contextlib.suppress(TransportValidationError):
            await asyncio.wait_for(task, timeout=1.0)

    # Inventory storm.
    for i in range(20):
        inv = InventoryMessage(inv_type="blocks", hashes=[f"{i:064x}"])
        honest_peer.relay.handle_inv("storm", inv.to_payload(), now=0.0)

    # Orphan storm.
    for i in range(12):
        temp = type(adversarial_peer.ledger)(chain=list(honest_peer.ledger.chain))
        block = mine_adversarial_block(temp, [{"id": f"orphan-{i}"}])
        honest_peer.relay.add_orphan(block, "storm", now=0.0)

    assert manager.available_slots >= 0
    assert table.size <= table._max_entries
    assert len(honest_peer.relay._orphans) <= honest_peer.relay._limits.max_orphan_blocks
    assert honest_peer.ledger.height() == 0


def test_reconnect_then_inventory_then_orphan_storm(honest_peer: SimulatedPeer, adversarial_peer: SimulatedPeer) -> None:
    asyncio.run(_run_reconnect_inventory_orphan_storm(honest_peer, adversarial_peer))


def test_invalid_block_through_sync_then_relay_never_commits(honest_peer: SimulatedPeer, adversarial_peer: SimulatedPeer) -> None:
    invalid = adversarial_peer.mine_adversarial([{"id": "bad"}])
    invalid.transactions.append({"id": "bad"})  # duplicate breaks consensus

    # Try sync entry point.
    honest_peer.sync.start_header_sync()
    sync_resp = honest_peer.sync.handle_headers(
        "adversarial",
        honest_peer.build_headers_message([invalid]).to_payload(),
    )
    assert sync_resp["status"] != "committed"

    # Try relay entry point.
    relay_resp = honest_peer.relay.handle_block(
        "adversarial",
        honest_peer.build_block_message(invalid).to_payload(),
        now=0.0,
    )
    assert any(r["status"] == "invalid" for r in relay_resp["results"])

    # No commitment anywhere.
    assert honest_peer.ledger.height() == 0
    assert invalid.hash not in honest_peer.relay._local_blocks_to_announce
    assert invalid.hash not in honest_peer.relay._seen_cache._cache
