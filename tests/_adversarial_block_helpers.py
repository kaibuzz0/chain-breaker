"""Shared helpers for adversarial tests that need to mine invalid blocks."""

from __future__ import annotations

from typing import Any

from chainbreaker.block import BlockHeaderV2, BlockV2
from chainbreaker.chain import Ledger
from chainbreaker.crypto import HashEngine, MerkleTree
from chainbreaker.registry_state import registry_root


def mine_adversarial_block(ledger: Ledger, transactions: list[dict[str, Any]]) -> BlockV2:
    """Mine a v2 block carrying arbitrary (possibly schema-invalid) transactions.

    This bypasses ``Ledger.mine_block_v2`` so adversarial tests can construct
    malformed blocks and assert that the network/consensus layers reject them.
    """
    tx_hashes = [HashEngine.hash_object(tx) for tx in transactions]
    merkle_root_hex = HashEngine.hex(MerkleTree(tx_hashes).root or bytes(32))
    previous_state = ledger.registry_state_at(ledger.height())
    header = BlockHeaderV2(
        version=2,
        prev_hash=ledger.last_block.hash,
        merkle_root=merkle_root_hex,
        registry_root=registry_root(previous_state),
        timestamp=ledger.next_block_timestamp(),
        target=ledger.expected_target_at(ledger.height() + 1),
        nonce=0,
    )
    header.mine()
    return BlockV2(header=header, transactions=transactions)
