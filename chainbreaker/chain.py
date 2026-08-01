
"""Ledger and chain validation with 256-bit target and retarget rules."""

from __future__ import annotations

import time
from typing import Any, Callable

from .block import (
    GENESIS_TARGET,
    MAX_TARGET,
    MIN_TARGET,
    NETWORK_ID,
    Block,
    BlockHeader,
    create_genesis_block,
)
from .codec import BinaryCodec, validate_transaction
from .crypto import HashEngine, MerkleTree, work_for_target

TARGET_BLOCK_TIME = 600
DIFFICULTY_RETARGET_INTERVAL = 10
MAX_RETARGET_FACTOR = 4


class LedgerError(ValueError):
    pass


class Ledger:
    """A proof-of-work ledger."""

    def __init__(self, chain: list[Block] | None = None,
                 transaction_validator: Callable[[dict[str, Any]], bool] | None = None,
                 max_block_size: int = 1_000_000,
                 max_transactions: int = 10_000,
                 network_id: str | None = None):
        if chain is None:
            chain = [create_genesis_block(network_id=network_id)]
        self.chain = list(chain)
        self.network_id = network_id or NETWORK_ID
        self.transaction_validator = transaction_validator
        self.max_block_size = max_block_size
        self.max_transactions = max_transactions

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    def height(self) -> int:
        return len(self.chain) - 1

    def genesis_hash(self) -> str:
        return self.chain[0].hash

    def median_past_time(self, end: int, count: int = 11) -> int:
        """Median timestamp of the previous `count` blocks ending at `end`."""
        end = min(end, len(self.chain))
        start = max(0, end - count)
        if start >= end:
            return 0
        timestamps = sorted(self.chain[i].header.timestamp for i in range(start, end))
        return timestamps[(len(timestamps) - 1) // 2]

    def next_block_timestamp(self) -> int:
        """Choose a timestamp valid under the median-past rule."""
        last_ts = self.last_block.header.timestamp
        median = self.median_past_time(len(self.chain))
        now = int(time.time())
        return max(
            now,
            last_ts + 1,
            median + 1,
        )

    def expected_target_at(self, height: int) -> int:
        """Pure function: expected proof-of-work target at a given height."""
        if height <= 0:
            return GENESIS_TARGET
        if height < DIFFICULTY_RETARGET_INTERVAL:
            return self.chain[0].header.target
        if height % DIFFICULTY_RETARGET_INTERVAL != 0:
            return self.chain[height - 1].header.target
        return self.retarget(height)

    def retarget(self, height: int) -> int:
        """Calculate target at a retarget boundary.

        Uses the window of `DIFFICULTY_RETARGET_INTERVAL` blocks ending at
        `height - 1`, compared against the block immediately preceding the
        window. For the first retarget at height {DIFFICULTY_RETARGET_INTERVAL},
        the preceding block is the genesis block.
        """
        if height < DIFFICULTY_RETARGET_INTERVAL:
            return GENESIS_TARGET
        prev_index = height - DIFFICULTY_RETARGET_INTERVAL - 1
        first_block = self.chain[prev_index + 1]
        last_block = self.chain[height - 1]
        prev_target = self.chain[height - 1].header.target
        actual_time = last_block.header.timestamp - first_block.header.timestamp
        if actual_time <= 0:
            actual_time = 1
        expected_time = TARGET_BLOCK_TIME * DIFFICULTY_RETARGET_INTERVAL
        new_target = (prev_target * actual_time) // expected_time
        # Clamp to absolute bounds
        new_target = max(MIN_TARGET, min(MAX_TARGET, new_target))
        # Clamp to per-retarget factor-of-4 limits
        max_allowed = prev_target * MAX_RETARGET_FACTOR
        min_allowed = prev_target // MAX_RETARGET_FACTOR
        new_target = max(min_allowed, min(max_allowed, new_target))
        return new_target

    def mine_block(self,
                   transactions: list[dict[str, Any]],
                   max_iterations: int = 10_000_000,
                   coinbase: dict[str, Any] | None = None,
                   timestamp: int | None = None) -> Block:
        """Create and mine a new block."""
        if coinbase is not None:
            transactions = [coinbase] + list(transactions)

        for tx in transactions:
            validate_transaction(tx)

        prev_hash = self.last_block.hash
        height = self.height() + 1
        target = self.expected_target_at(height)
        if timestamp is None:
            timestamp = self.next_block_timestamp()

        # Compute Merkle root
        tx_hashes = [HashEngine.hash_object(tx) for tx in transactions]
        merkle_root = MerkleTree(tx_hashes).root or bytes(32)
        merkle_root_hex = HashEngine.hex(merkle_root)

        header = BlockHeader(
            version=1,
            prev_hash=prev_hash,
            merkle_root=merkle_root_hex,
            timestamp=timestamp,
            target=target,
            nonce=0,
        )
        block = Block(header, list(transactions))
        if not block.mine(max_iterations=max_iterations):
            raise LedgerError("mining failed to find proof of work")
        return block

    def add_block(self, block: Block) -> bool:
        """Validate and append a block to the chain."""
        expected_height = self.height() + 1
        expected_target = self.expected_target_at(expected_height)
        expected_prev_hash = self.last_block.hash

        # Basic structural checks
        if block.header.prev_hash != expected_prev_hash:
            return False
        if block.header.target != expected_target:
            return False

        median = self.median_past_time(len(self.chain))
        now = int(time.time())

        if not block.verify(
            reference_time=now,
            median_past=median,
            expected_target=expected_target,
            transaction_validator=self.transaction_validator,
        ):
            return False

        self.chain.append(block)
        return True

    def validate_chain(self, *, from_height: int = 0) -> bool:
        """Full validation of the chain from genesis up."""
        if not self.chain:
            return False
        genesis = self.chain[0]
        if not genesis.is_genesis():
            return False
        if not genesis.verify(allow_genesis=True):
            return False

        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

            # Previous hash links to recomputed hash
            if current.header.prev_hash != previous.hash:
                return False

            # Difficulty
            expected_target = self.expected_target_at(i)
            if current.header.target != expected_target:
                return False

            # Median-past rule
            median = self.median_past_time(i)
            if current.header.timestamp <= median:
                return False

            # Not too far in the future
            if current.header.timestamp > int(time.time()) + 7200:
                return False

            # PoW and Merkle
            if not current.verify(
                median_past=median,
                expected_target=expected_target,
                transaction_validator=self.transaction_validator,
            ):
                return False

        return True

    def chain_work(self) -> float:
        return sum(work_for_target(b.header.target) for b in self.chain)

    def to_dict(self) -> dict[str, Any]:
        return {
            "network_id": NETWORK_ID,
            "chain": [b.to_dict() for b in self.chain],
            "chain_work": self.chain_work(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any],
                  transaction_validator: Callable[[dict[str, Any]], bool] | None = None) -> Ledger:
        if data.get("network_id") != NETWORK_ID:
            raise LedgerError("invalid network ID")
        chain = [Block.from_dict(b) for b in data["chain"]]
        return cls(chain, transaction_validator=transaction_validator)


def block_encode(block: Block) -> bytes:
    """Encode a block for network/storage."""
    header_bytes = BinaryCodec.encode_header(block.header.to_dict())
    tx_count = BinaryCodec.encode_varint(len(block.transactions))
    tx_bytes = b"".join(BinaryCodec.encode_transaction(tx) for tx in block.transactions)
    return header_bytes + tx_count + tx_bytes


def block_decode(data: bytes) -> tuple[Block, int]:
    """Decode a block."""
    header, offset = BinaryCodec.decode_header(data)
    tx_count, offset = BinaryCodec.decode_varint(data, offset)
    transactions = []
    for _ in range(tx_count):
        tx, offset = BinaryCodec.decode_transaction(data, offset)
        transactions.append(tx)
    return Block(BlockHeader.from_dict(header), transactions), offset
