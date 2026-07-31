
"""Block structure, proof-of-work, and validation.

Rules:
- Block hash is always recomputed; never trusted from serialization.
- Genesis block has immutable, hard-coded specification.
- Timestamp rule rejects blocks too far in the future;
  historical validity is preserved by using median-past rule.
- Difficulty is exact per block, not a lower bound.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from .crypto import HashEngine, MerkleTree
from .codec import BinaryCodec


PROTOCOL_VERSION = 1
NETWORK_ID = "chainbreaker-scripture-v1"
GENESIS_MESSAGE = "Chain-Breaker Genesis: scripture preservation ledger"
GENESIS_TIMESTAMP = 1704067200  # 2024-01-01 00:00:00 UTC
GENESIS_DIFFICULTY = 16  # bits; represented as leading zero hex chars for display


def difficulty_to_leading_zeros(difficulty_bits: int) -> int:
    """Convert difficulty bits to number of leading hex zeros needed.

    1 hex zero == 4 bits. This is the canonical interpretation.
    """
    return difficulty_bits // 4


@dataclass
class BlockHeader:
    version: int
    prev_hash: str
    merkle_root: str
    timestamp: int  # Unix seconds
    difficulty: int  # bits
    nonce: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BlockHeader:
        return cls(
            version=int(data["version"]),
            prev_hash=str(data["prev_hash"]),
            merkle_root=str(data["merkle_root"]),
            timestamp=int(data["timestamp"]),
            difficulty=int(data["difficulty"]),
            nonce=int(data["nonce"]),
        )

    def hash(self) -> str:
        """Recompute block header hash from canonical bytes."""
        header_bytes = BinaryCodec.encode_header(self.to_dict())
        return HashEngine.hash_bytes(HashEngine.double_sha256(header_bytes))


@dataclass
class Block:
    header: BlockHeader
    transactions: List[Dict[str, Any]]

    def calculate_hash(self) -> str:
        return self.header.hash()

    @property
    def hash(self) -> str:
        """Hash is a computed property, never stored."""
        return self.calculate_hash()

    def merkle_root(self) -> str:
        if not self.transactions:
            return "0" * 64
        tx_hashes = [HashEngine.hash_object(tx) for tx in self.transactions]
        root = MerkleTree(tx_hashes).root
        return HashEngine.hex(root) if root else "0" * 64

    def verify(self, *, reference_time: Optional[int] = None,
               allow_genesis: bool = False,
               median_past: Optional[int] = None) -> bool:
        """Verify block integrity independently of chain context."""
        # Recompute and check merkle root
        if self.merkle_root() != self.header.merkle_root:
            return False

        # Recompute and check proof-of-work
        leading_zeros = difficulty_to_leading_zeros(self.header.difficulty)
        if not self.hash.startswith("0" * leading_zeros):
            return False

        if allow_genesis and self.is_genesis():
            return self._verify_genesis()

        # Future-timestamp bound
        now = reference_time or int(time.time())
        if self.header.timestamp > now + 7200:
            return False

        # Median-past rule (historical blocks remain valid)
        if median_past is not None and self.header.timestamp <= median_past:
            return False

        return True

    def is_genesis(self) -> bool:
        return self.header.prev_hash == "0" * 64

    def _verify_genesis(self) -> bool:
        """Hard-coded genesis check."""
        expected = create_genesis_block()
        return (
            self.header.version == expected.header.version
            and self.header.prev_hash == expected.header.prev_hash
            and self.header.timestamp == expected.header.timestamp
            and self.header.difficulty == expected.header.difficulty
            and self.header.nonce == expected.header.nonce
            and self.header.merkle_root == expected.header.merkle_root
            and self.transactions == expected.transactions
            and self.hash == expected.hash
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "header": self.header.to_dict(),
            "transactions": self.transactions,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Block:
        header = BlockHeader.from_dict(data["header"])
        # Ignore any stored hash; recompute.
        return cls(header=header, transactions=list(data.get("transactions", [])))

    def mine(self, max_iterations: int = 10_000_000) -> bool:
        """Find a nonce satisfying the difficulty target."""
        target = "0" * difficulty_to_leading_zeros(self.header.difficulty)
        for _ in range(max_iterations):
            if self.hash.startswith(target):
                return True
            self.header.nonce += 1
        return False


def create_genesis_block() -> Block:
    """Create the canonical genesis block."""
    genesis_tx = {
        "version": PROTOCOL_VERSION,
        "type": "genesis",
        "body": {
            "network_id": NETWORK_ID,
            "message": GENESIS_MESSAGE,
            "timestamp": GENESIS_TIMESTAMP,
        },
        "witnesses": [],
    }
    header = BlockHeader(
        version=PROTOCOL_VERSION,
        prev_hash="0" * 64,
        merkle_root="0" * 64,
        timestamp=GENESIS_TIMESTAMP,
        difficulty=GENESIS_DIFFICULTY,
        nonce=0,
    )
    block = Block(header=header, transactions=[genesis_tx])
    block.header.merkle_root = block.merkle_root()
    block.mine()
    return block
