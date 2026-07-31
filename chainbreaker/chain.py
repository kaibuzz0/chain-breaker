
"""Ledger with proof-of-work, chain validation, and difficulty adjustment."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .block import Block, BlockHeader, create_genesis_block
from .crypto import HashEngine, MerkleTree


TARGET_BLOCK_TIME = 600  # seconds
DIFFICULTY_RETARGET_INTERVAL = 10
MIN_DIFFICULTY = 8
MAX_DIFFICULTY = 256


class ChainError(ValueError):
    """Raised when chain rules are violated."""


class Ledger:
    """Append-only ledger with deterministic validation."""

    def __init__(self, chain: Optional[List[Block]] = None):
        self.chain: List[Block] = chain or [create_genesis_block()]

    @property
    def height(self) -> int:
        return len(self.chain) - 1

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    def median_past_time(self, end: Optional[int] = None, count: int = 11) -> int:
        # Median timestamp of the ``count`` blocks immediately preceding ``end``.
        end = end if end is not None else len(self.chain)
        start = max(0, end - count)
        timestamps = sorted(b.header.timestamp for b in self.chain[start:end])
        return timestamps[len(timestamps) // 2]

    def get_next_difficulty(self) -> int:
        if len(self.chain) < DIFFICULTY_RETARGET_INTERVAL + 1:
            return self.chain[0].header.difficulty

        first = self.chain[-DIFFICULTY_RETARGET_INTERVAL - 1]
        last = self.last_block
        actual_time = last.header.timestamp - first.header.timestamp
        expected_time = TARGET_BLOCK_TIME * DIFFICULTY_RETARGET_INTERVAL
        if actual_time <= 0:
            actual_time = 1

        old_diff = last.header.difficulty
        new_diff = int(old_diff * expected_time / actual_time)
        return max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, new_diff))

    def validate_chain(self) -> bool:
        for i, block in enumerate(self.chain):
            if i == 0:
                if not block.verify(allow_genesis=True):
                    return False
                continue

            previous = self.chain[i - 1]
            median_past = self.median_past_time(end=i, count=min(11, i))
            if not block.verify(median_past=median_past):
                return False

            expected_difficulty = self._expected_difficulty_at(i)
            if block.header.difficulty != expected_difficulty:
                return False

            if block.header.prev_hash != previous.hash:
                return False

        return True

    def _expected_difficulty_at(self, index: int) -> int:
        if index == 0:
            return self.chain[0].header.difficulty
        if index % DIFFICULTY_RETARGET_INTERVAL != 0:
            return self.chain[index - 1].header.difficulty
        ledger = Ledger(self.chain[:index])
        return ledger.get_next_difficulty()

    def add_block(self, block: Block) -> None:
        if block.header.prev_hash != self.last_block.hash:
            raise ChainError("block does not link to current tip")
        expected_difficulty = self.get_next_difficulty()
        if block.header.difficulty != expected_difficulty:
            raise ChainError(f"difficulty {block.header.difficulty} != expected {expected_difficulty}")
        if not block.verify(median_past=self.median_past_time(end=len(self.chain))):
            raise ChainError("block verification failed")
        self.chain.append(block)

    def mine_block(self, transactions: List[Dict[str, Any]],
                   max_iterations: int = 10_000_000) -> Block:
        tx_hashes = [HashEngine.hash_object(tx) for tx in transactions]
        root = MerkleTree(tx_hashes).root
        merkle_root = HashEngine.hex(root) if root else "0" * 64
        header = BlockHeader(
            version=1,
            prev_hash=self.last_block.hash,
            merkle_root=merkle_root,
            timestamp=max(
                self.last_block.header.timestamp + TARGET_BLOCK_TIME,
                self.median_past_time(end=len(self.chain)) + 1,
            ),
            difficulty=self.get_next_difficulty(),
            nonce=0,
        )
        block = Block(header=header, transactions=transactions)
        if not block.mine(max_iterations=max_iterations):
            raise ChainError("mining failed to find a nonce")
        self.add_block(block)
        return block

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blocks": [b.to_dict() for b in self.chain],
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Ledger:
        return cls(chain=[Block.from_dict(b) for b in data["blocks"]])
