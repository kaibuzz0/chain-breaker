"""
Chain-Breaker Block Module
==========================

Core block data structure with E8-enhanced hashing.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import time
import json

# Import E8 hasher
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from chain_breaker.crypto.e8_hash import E8BlockHasher


@dataclass
class Block:
    """
    A block in the Chain-Breaker blockchain.
    
    Uses E8-enhanced hashing for quantum-resistant chain linking.
    """
    index: int
    timestamp: float
    data: str
    previous_hash: str
    hash: str = ""
    nonce: int = 0
    difficulty: int = 100
    merkle_root: Optional[str] = None
    
    def __post_init__(self):
        if not self.hash:
            self.compute_hash()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize block to dictionary."""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
            "merkle_root": self.merkle_root
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Block":
        """Deserialize block from dictionary."""
        return cls(
            index=data["index"],
            timestamp=data["timestamp"],
            data=data["data"],
            previous_hash=data["previous_hash"],
            hash=data.get("hash", ""),
            nonce=data.get("nonce", 0),
            difficulty=data.get("difficulty", 100),
            merkle_root=data.get("merkle_root")
        )
    
    def compute_hash(self) -> str:
        """Compute E8-enhanced block hash."""
        hasher = E8BlockHasher()
        self.hash = hasher.hash_block(self.to_dict(), self.nonce)
        return self.hash
    
    def validate(self) -> bool:
        """Validate block integrity."""
        # Recompute hash and verify
        computed = self.compute_hash()
        return computed == self.hash
    
    def __str__(self) -> str:
        """String representation."""
        return f"Block(#{self.index}, {self.data[:30]}..., {self.hash[:16]}...)"


class BlockValidator:
    """Mobile-optimized block validation."""
    
    @staticmethod
    def validate_chain_continuity(prev_block: Block, current_block: Block) -> bool:
        """Validate that blocks form a continuous chain."""
        # Check index continuity
        if current_block.index != prev_block.index + 1:
            return False
        
        # Check hash link
        if current_block.previous_hash != prev_block.hash:
            return False
        
        # Check timestamp is reasonable
        if current_block.timestamp < prev_block.timestamp:
            return False
        
        return True
    
    @staticmethod
    def validate_difficulty(block: Block, expected_difficulty: int) -> bool:
        """Validate block meets difficulty target."""
        from chain_breaker.crypto.e8_hash import DifficultyCalculator
        
        calc = DifficultyCalculator()
        return calc.check_proof_of_work(block.hash, expected_difficulty)
