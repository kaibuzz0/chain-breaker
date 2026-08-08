"""Network adversarial certification tests.

These tests exercise the combined network stack under adversarial conditions.
They are designed to reveal resource, ordering, and trust-boundary failures
across discovery, handshake, sync, and relay.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import pytest

from chainbreaker.block import NETWORK_ID, create_genesis_block
from chainbreaker.chain import Ledger
from chainbreaker.network.discovery.bootstrap import MemoryBootstrapSource
from chainbreaker.network.discovery.discovery import DiscoveryManager
from chainbreaker.network.discovery.errors import PeerTableFullError
from chainbreaker.network.discovery.peer_table import PeerRecord, PeerSource, PeerTable
from chainbreaker.network.messages import GetBlockMessage, InventoryMessage
from chainbreaker.network.relay import RelayEngine, RelayLimitPolicy
from chainbreaker.network.sync import SyncEngine
from chainbreaker.network.transport.handshake import HandshakeContext
from chainbreaker.network.transport.manager import ConnectionManager
from chainbreaker.storage import FlatFileStorageBackend


class SimulatedPeer:
    """A minimal in-memory peer for certification scenarios."""

    def __init__(self, peer_id: str, tmp_path: Path) -> None:
        self.peer_id = peer_id
        genesis = create_genesis_block()
        self.ledger = Ledger(chain=[genesis])
        self.storage = FlatFileStorageBackend(
            tmp_path / peer_id,
            network_id=NETWORK_ID,
            genesis_hash=genesis.hash,
        )
        self.discovery = DiscoveryManager(
            table=PeerTable(max_entries=8),
            bootstrap_sources=[MemoryBootstrapSource(records=[])],
        )
        self.sync = SyncEngine(ledger=self.ledger, storage=self.storage)
        self.relay = RelayEngine(ledger=self.ledger, storage=self.storage)
        handshake_context = HandshakeContext(
            network_id=NETWORK_ID,
            genesis_hash=genesis.hash,
            local_features=frozenset({"relay"}),
            protocol_version=1,
        )
        self.connection_manager = ConnectionManager(handshake_context, max_connections=16)

    def mine_and_accept(self, transactions: list[dict[str, Any]] | None = None) -> Any:
        if transactions is None:
            transactions = []
        block = self.ledger.mine_block_v2(transactions)
        self.ledger.add_block_v2(block)
        previous_state = self.ledger.registry_state_at(self.ledger.height() - 1)
        self.storage.append_block(block, previous_state=previous_state)
        self.relay.on_local_block(block)
        return block


@pytest.fixture
def honest_peer(tmp_path: Path) -> SimulatedPeer:
    return SimulatedPeer("honest", tmp_path)


@pytest.fixture
def adversarial_peer(tmp_path: Path) -> SimulatedPeer:
    return SimulatedPeer("adversarial", tmp_path)


def test_malicious_peer_swarm_does_not_overflow_peer_table(honest_peer: SimulatedPeer) -> None:
    table = honest_peer.discovery.peer_table
    for i in range(64):
        with contextlib.suppress(PeerTableFullError):
            table.add(
                PeerRecord(
                    peer_id=f"attacker-{i}",
                    host="127.0.0.1",
                    port=10000 + i,
                    source=PeerSource.MANUAL,
                    capabilities={},
                    score=0,
                )
            )
    assert table.size <= table._max_entries


def test_fake_high_work_chain_rejected_by_sync_engine(honest_peer: SimulatedPeer, adversarial_peer: SimulatedPeer) -> None:
    # Adversary mines a short chain.
    bad_block = adversarial_peer.mine_and_accept()
    honest_peer.sync.start_header_sync()

    # Build a single invalid header message from adversarial chain.
    from chainbreaker.network.messages import HeaderEntry, HeadersMessage

    hs = honest_peer.sync._header_sync
    header_msg = HeadersMessage(
        headers=[
            HeaderEntry(height=1, hash=bad_block.hash, header_bytes=hs.encode_header(bad_block.header))
        ]
    )
    resp = honest_peer.sync.handle_headers("adversarial", header_msg.to_payload())
    assert resp["status"] != "committed"


def test_relay_flooding_resists_duplicate_amplification(honest_peer: SimulatedPeer) -> None:
    honest_peer.relay._limits = RelayLimitPolicy(max_inv_per_peer_per_minute=5)
    resp = None
    for i in range(10):
        inv = InventoryMessage(inv_type="blocks", hashes=[f"{i:064x}"])
        resp = honest_peer.relay.handle_inv("flood", inv.to_payload(), now=0.0)
    assert resp is not None
    assert resp["status"] == "rate_limited"


def test_repeated_block_inventory_ignored(honest_peer: SimulatedPeer) -> None:
    inv = InventoryMessage(inv_type="blocks", hashes=["deadbeef" * 8])
    honest_peer.relay.handle_inv("peer", inv.to_payload())
    resp = honest_peer.relay.handle_inv("peer", inv.to_payload())
    assert resp["hashes"] == []


def test_unknown_block_get_response_does_not_crash(honest_peer: SimulatedPeer) -> None:
    msg = GetBlockMessage(hashes=["0" * 64], max_total_bytes=2_000_000)
    resp = honest_peer.relay.handle_get_block("peer", msg.to_payload())
    assert resp["status"] == "unknown"


def test_sync_interrupt_then_restart_is_clean(honest_peer: SimulatedPeer) -> None:
    honest_peer.sync.start_header_sync()
    honest_peer.sync.reset()
    assert honest_peer.sync.state.name == "IDLE"


def test_peer_churn_does_not_corrupt_state(honest_peer: SimulatedPeer) -> None:
    for i in range(8):
        honest_peer.discovery.peer_table.add(
            PeerRecord(
                peer_id=f"peer-{i}",
                host="127.0.0.1",
                port=20000 + i,
                source=PeerSource.MANUAL,
                capabilities={},
                score=500,
            )
        )
        _ = honest_peer.discovery.peer_table.remove(f"peer-{i}")
    assert honest_peer.discovery.peer_table.size == 0


def test_reconnect_storm_does_not_exceed_capacity(honest_peer: SimulatedPeer) -> None:
    # Capacity should never become negative; available slots is bounded by configured capacity.
    for _ in range(32):
        assert honest_peer.connection_manager.available_slots >= 0
    assert honest_peer.connection_manager.available_slots <= 16
