"""
block_core.py

Block structure and validation.
- BlockHeader: Metadata (prev_hash, merkle_root, timestamp, nonce)
- Block: Header + transactions
- Validation rules
"""

import time
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from .hash_engine import HashEngine, MerkleTree


@dataclass
class BlockHeader:
    """
    Block metadata forming the chain link.
    
    Fields:
    - version: Protocol version
    - prev_hash: Hash of previous block (chain integrity)
    - merkle_root: Root of transaction Merkle tree
    - timestamp: Unix timestamp
    - difficulty: Mining difficulty target
    - nonce: Proof-of-work nonce
    """
    version: int = 1
    prev_hash: str = "0" * 64  # Genesis block default
    merkle_root: str = "0" * 64
    timestamp: float = 0.0
    difficulty: int = 4  # Number of leading zeros required
    nonce: int = 0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def hash(self) -> str:
        """Hash of this header (block identity)."""
        header_bytes = json.dumps(self.to_dict(), sort_keys=True).encode()
        return HashEngine.hash_to_hex(HashEngine.double_sha256(header_bytes))
    
    def get_hash_target(self) -> str:
        """Difficulty target as hex string."""
        return "0" * self.difficulty + "f" * (64 - self.difficulty)


@dataclass 
class Block:
    """
    Complete block with transactions.
    
    Structure:
    - header: BlockHeader metadata
    - transactions: List of transaction dicts
    - hash: Cached block hash
    """
    header: BlockHeader
    transactions: List[Dict[str, Any]]
    hash: Optional[str] = None
    
    def __post_init__(self):
        if self.hash is None:
            self.hash = self.calculate_hash()
    
    def calculate_hash(self) -> str:
        """Calculate block hash from header."""
        return self.header.hash()
    
    def verify(self) -> bool:
        """
        Verify block integrity.
        
        Checks:
        1. Merkle root matches transactions
        2. Hash meets difficulty target
        3. Timestamp reasonable
        """
        # Verify Merkle root
        if self.transactions:
            tx_hashes = [HashEngine.hash_object(tx) for tx in self.transactions]
            tree = MerkleTree(tx_hashes)
            if tree.root is None:
                return False
            expected_root = HashEngine.hash_to_hex(tree.root)
            if expected_root != self.header.merkle_root:
                return False
        
        # Verify difficulty
        if not self.hash.startswith("0" * self.header.difficulty):
            return False
        
        # Verify timestamp (within 2 hours of now)
        if abs(time.time() - self.header.timestamp) > 7200:
            return False
        
        return True
    
    def mine(self) -> bool:
        """
        Proof-of-work mining.
        Find nonce such that hash meets difficulty target.
        """
        target = "0" * self.header.difficulty
        
        while not self.hash.startswith(target):
            self.header.nonce += 1
            self.hash = self.calculate_hash()
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "header": self.header.to_dict(),
            "transactions": self.transactions,
            "hash": self.hash,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Block':
        """Deserialize from dictionary."""
        header = BlockHeader(**data["header"])
        return cls(
            header=header,
            transactions=data["transactions"],
            hash=data.get("hash")
        )


def create_genesis_block() -> Block:
    """
    Create the genesis block (first block in chain).
    """
    genesis_time = 0  # Epoch
    genesis_tx = {
        "type": "genesis",
        "message": "Chain-Breaker Genesis",
        "timestamp": genesis_time,
    }
    
    header = BlockHeader(
        version=1,
        prev_hash="0" * 64,
        merkle_root="0" * 64,  # Simplified for genesis
        timestamp=genesis_time,
        difficulty=1,  # Easy for genesis
        nonce=0,
    )
    
    block = Block(header=header, transactions=[genesis_tx])
    block.mine()  # Mine genesis block
    
    return block


if __name__ == "__main__":
    print("Block Test")
    
    # Genesis block
    genesis = create_genesis_block()
    print(f"Genesis hash: {genesis.hash[:16]}...")
    print(f"Verified: {genesis.verify()}")
    
    # New block
    tx = {"from": "alice", "to": "bob", "amount": 50}
    tx_hash = HashEngine.hash_object(tx)
    merkle = MerkleTree([tx_hash])
    
    header = BlockHeader(
        version=1,
        prev_hash=genesis.hash,
        merkle_root=HashEngine.hash_to_hex(merkle.root) if merkle.root else "0" * 64,
        difficulty=2,
    )
    
    block = Block(header=header, transactions=[tx])
    print(f"\nMining block with difficulty {header.difficulty}...")
    block.mine()
    
    print(f"Block hash: {block.hash[:16]}...")
    print(f"Verified: {block.verify()}")
    print(f"Nonce: {block.header.nonce}")
