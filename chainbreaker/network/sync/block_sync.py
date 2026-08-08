"""Block synchronization logic."""

from __future__ import annotations

import json

from chainbreaker.block import BlockV2
from chainbreaker.chain import Ledger
from chainbreaker.network.messages import BlockMessage, GetBlockMessage
from chainbreaker.network.sync.errors import SyncInvalidDataError


class BlockSync:
    """Download and validate full blocks for a validated header chain."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    def create_get_block(self, block_hash: str) -> GetBlockMessage:
        return GetBlockMessage(hashes=[block_hash], max_total_bytes=2_000_000)

    def parse_block_message(self, message: BlockMessage, expected_height: int, expected_prev_hash: str) -> BlockV2:
        """Parse and structurally validate a single-block response."""
        if len(message.blocks) != 1:
            raise SyncInvalidDataError("expected exactly one block in response")
        entry = message.blocks[0]
        try:
            block = self._decode_block(entry["block_bytes"])
        except Exception as exc:
            raise SyncInvalidDataError(f"block decode failed: {exc}") from exc

        if block.header.prev_hash != expected_prev_hash:
            raise SyncInvalidDataError("block prev_hash mismatch")
        expected_target = self._ledger.expected_target_at(expected_height)
        if block.header.target != expected_target:
            raise SyncInvalidDataError("block target mismatch")

        return block

    def _decode_block(self, block_bytes_hex: str) -> BlockV2:
        data = json.loads(bytes.fromhex(block_bytes_hex).decode("utf-8"))
        return BlockV2.from_dict(data)

    def encode_block(self, block: BlockV2) -> str:
        """Serialize a block to a hex string for wire transport."""
        return json.dumps(block.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8").hex()
