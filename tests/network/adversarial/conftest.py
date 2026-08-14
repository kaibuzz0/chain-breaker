"""Shared fixtures and harness for network adversarial certification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from chainbreaker.block import NETWORK_ID, BlockV2, create_genesis_block
from chainbreaker.chain import Ledger
from chainbreaker.network.discovery.bootstrap import MemoryBootstrapSource
from chainbreaker.network.discovery.discovery import DiscoveryManager
from chainbreaker.network.discovery.peer_table import PeerTable
from chainbreaker.network.messages import (
    BlockMessage,
    GetBlockMessage,
    HeaderEntry,
    HeadersMessage,
    InventoryMessage,
)
from chainbreaker.network.relay import RelayEngine
from chainbreaker.network.sync import SyncEngine
from chainbreaker.network.transport.handshake import HandshakeContext
from chainbreaker.network.transport.manager import ConnectionManager
from chainbreaker.storage import FlatFileStorageBackend


class SimulatedPeer:
    """A minimal in-memory peer for combined-stack adversarial tests."""

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
        self.handshake_context = HandshakeContext(
            network_id=NETWORK_ID,
            genesis_hash=genesis.hash,
            local_features=frozenset({"relay", "headers", "blocks"}),
            protocol_version=1,
        )
        self.connection_manager = ConnectionManager(
            self.handshake_context,
            max_connections=16,
        )

    def mine_and_accept(
        self, transactions: list[dict[str, Any]] | None = None
    ) -> Any:
        """Mine a block, validate it, store it, and queue it for relay."""
        if transactions is None:
            transactions = []
        block = self.ledger.mine_block_v2(transactions)
        self.ledger.add_block_v2(block)
        previous_state = self.ledger.registry_state_at(self.ledger.height() - 1)
        self.storage.append_block(block, previous_state=previous_state)
        self.relay.on_local_block(block)
        return block

    def mine_adversarial(self, transactions: list[dict[str, Any]]) -> BlockV2:
        """Create an adversarial block with arbitrary transactions.

        The block is *not* accepted locally; callers use it to test rejection
        by sync, relay, or consensus.
        """
        from tests._adversarial_block_helpers import mine_adversarial_block
        return mine_adversarial_block(self.ledger, transactions)

    def build_headers_message(self, blocks: list[Any]) -> HeadersMessage:
        """Build a HEADERS message from a list of blocks."""
        # Use the first block's height if available; otherwise start after the
        # current local ledger tip.
        first_height = getattr(blocks[0].header, "height", None)
        start_height = first_height if first_height is not None else self.ledger.height() + 1
        entries = [
            HeaderEntry(
                height=start_height + i,
                hash=block.hash,
                header_bytes=self.sync._header_sync.encode_header(block.header),
            )
            for i, block in enumerate(blocks)
        ]
        return HeadersMessage(headers=entries)

    def build_block_message(self, block: Any) -> BlockMessage:
        """Build a BLOCK message from a single block."""
        return BlockMessage(
            blocks=[{
                "hash": block.hash,
                "block_bytes": self.sync._block_sync.encode_block(block),
            }]
        )

    def build_inv_message(self, hashes: list[str]) -> InventoryMessage:
        """Build an INV_BLOCK message."""
        return InventoryMessage(inv_type="blocks", hashes=hashes)

    def build_get_block_message(self, hashes: list[str]) -> GetBlockMessage:
        """Build a GET_BLOCK message."""
        return GetBlockMessage(hashes=hashes, max_total_bytes=2_000_000)


@pytest.fixture
def honest_peer(tmp_path: Path) -> SimulatedPeer:
    return SimulatedPeer("honest", tmp_path)


@pytest.fixture
def adversarial_peer(tmp_path: Path) -> SimulatedPeer:
    return SimulatedPeer("adversarial", tmp_path)
