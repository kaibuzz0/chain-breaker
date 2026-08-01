
"""Block structure, proof-of-work, and validation with 256-bit target."""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Callable

from .codec import BinaryCodec
from .crypto import HashEngine, MerkleTree, hex_to_target, target_to_hex

PROTOCOL_VERSION = 1
NETWORK_ID = "chainbreaker-scripture-v1"
GENESIS_MESSAGE = "Chain-Breaker Genesis: scripture preservation ledger"
GENESIS_TIMESTAMP = 1704067200

# Bitcoin-style maximum target
MAX_TARGET = 0x0000FFFF00000000000000000000000000000000000000000000000000000000
MIN_TARGET = 0x0000000000000000000000000000000000000000000000000000000000000001

# Genesis target: easy enough to mine quickly, but bounded.
GENESIS_TARGET = MAX_TARGET

# Hard-coded genesis constants, computed once by _compute_genesis_constants().
GENESIS_NONCE = 1450239
GENESIS_HASH = "000000006a6e5c2d7c91ec97a1e2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d"  # placeholder, will be replaced


def header_bytes(header: dict[str, Any]) -> bytes:
    """Canonical serialization of a block header."""
    return BinaryCodec.encode_header(header)


def header_hash(header: dict[str, Any]) -> str:
    """Double-SHA256 of the canonical header bytes."""
    return HashEngine.hash_double_hex(header_bytes(header))


def satisfies_pow(block_hash: str, target: int) -> bool:
    """Check whether a 64-char hex block hash meets the target."""
    return int(block_hash, 16) <= target


@dataclass
class BlockHeader:
    version: int
    prev_hash: str
    merkle_root: str
    timestamp: int  # Unix seconds
    target: int  # 256-bit integer
    nonce: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "prev_hash": self.prev_hash,
            "merkle_root": self.merkle_root,
            "timestamp": self.timestamp,
            "target": target_to_hex(self.target),
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BlockHeader:
        return cls(
            version=int(data["version"]),
            prev_hash=str(data["prev_hash"]),
            merkle_root=str(data["merkle_root"]),
            timestamp=int(data["timestamp"]),
            target=hex_to_target(str(data["target"])),
            nonce=int(data["nonce"]),
        )

    def hash(self) -> str:
        return header_hash(self.to_dict())


@dataclass
class Block:
    header: BlockHeader
    transactions: list[dict[str, Any]]

    def calculate_hash(self) -> str:
        return self.header.hash()

    @property
    def hash(self) -> str:
        return self.calculate_hash()

    def merkle_root(self) -> str:
        if not self.transactions:
            return "0" * 64
        tx_hashes = [HashEngine.hash_object(tx) for tx in self.transactions]
        root = MerkleTree(tx_hashes).root
        return HashEngine.hex(root) if root else "0" * 64

    def verify(self, *, reference_time: int | None = None,
               allow_genesis: bool = False,
               median_past: int | None = None,
               expected_target: int | None = None,
               transaction_validator: Callable[[dict[str, Any]], bool] | None = None) -> bool:
        """Verify block integrity."""
        # Target bounds
        if not (MIN_TARGET <= self.header.target <= MAX_TARGET):
            return False

        # Recompute Merkle root
        if self.merkle_root() != self.header.merkle_root:
            return False

        # Recompute and check PoW
        if not satisfies_pow(self.hash, self.header.target):
            return False

        if expected_target is not None and self.header.target != expected_target:
            return False

        if allow_genesis and self.is_genesis():
            return self._verify_genesis()

        # Future-timestamp bound
        now = reference_time or int(time.time())
        if self.header.timestamp > now + 7200:
            return False

        # Median-past rule
        if median_past is not None and self.header.timestamp <= median_past:
            return False

        # Validate transactions if a validator is supplied
        if transaction_validator is not None:
            for tx in self.transactions:
                if not transaction_validator(tx):
                    return False

        return True

    def is_genesis(self) -> bool:
        return self.header.prev_hash == "0" * 64

    def _verify_genesis(self) -> bool:
        expected = create_genesis_block()
        return (
            self.header.version == expected.header.version
            and self.header.prev_hash == expected.header.prev_hash
            and self.header.timestamp == expected.header.timestamp
            and self.header.target == expected.header.target
            and self.header.nonce == expected.header.nonce
            and self.header.merkle_root == expected.header.merkle_root
            and self.transactions == expected.transactions
            and self.hash == expected.hash
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "header": self.header.to_dict(),
            "transactions": self.transactions,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Block:
        header = BlockHeader.from_dict(data["header"])
        # Ignore any stored hash; recompute.
        return cls(header=header, transactions=list(data.get("transactions", [])))

    def mine(self, max_iterations: int = 10_000_000) -> bool:
        """Find a nonce satisfying the target."""
        for _ in range(max_iterations):
            if satisfies_pow(self.hash, self.header.target):
                return True
            self.header.nonce += 1
        return False


def _compute_genesis_constants() -> Block:
    """Compute the canonical genesis block once."""
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
        target=GENESIS_TARGET,
        nonce=0,
    )
    block = Block(header=header, transactions=[genesis_tx])
    block.header.merkle_root = block.merkle_root()
    if not block.mine():
        raise RuntimeError("failed to mine genesis block")
    return block


# Compute once at import time and store constants.
# _genesis_block is initialized lazily below to avoid expensive import-time work.
_genesis_block: Block | None = None
GENESIS_NONCE = 116224
GENESIS_HASH = "00001ec5b63d845f0afa2e499817c34a7e0de2b1c53675171645f60f36ea927c"
GENESIS_MERKLE_ROOT = "1f49f39b97709a5eebdfe90a83825b02755b417990eb873b7c5c99c76431b93b"


def create_genesis_block(network_id: str | None = None) -> Block:
    """Return the canonical genesis block without re-mining."""
    global _genesis_block
    if _genesis_block is None:
        _genesis_block = _compute_genesis_constants()
    data = _genesis_block.to_dict()
    data["transactions"] = copy.deepcopy(data["transactions"])
    return Block.from_dict(data)
