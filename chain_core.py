#!/usr/bin/env python3
"""
Chain-Core: Blockchain structure and validation
Mobile-optimized with E8-enhanced hashing
"""

import hashlib
import json
import time
import struct
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
import numpy as np

from e8_core import E8Lattice
from e8_signature import HybridSignature, ScriptureAuthority

# Consensus parameters (optimized for mobile)
CONSENSUS = {
    "block_time": 300,           # 5 minutes (faster than Bitcoin's 10)
    "block_size": 262_144,       # 256KB max (mobile-friendly)
    "max_tx": 100,               # Max transactions per block
    "max_scripture_tx": 20,      # Scripture anchors per block
    "difficulty": 24,            # Initial difficulty (lower than Bitcoin)
    "retarget_interval": 2016,   # Difficulty adjust every ~1 week
    "min_witnesses": 3,          # For scripture anchors
    
    # E8 specific
    "e8_mining": True,           # Use E8 transformations in mining
    "e8_rounds": 5,              # Weyl reflections per hash
    
    # Storage
    "prune_after": 100_000,      # Blocks to keep full data
}


@dataclass
class Transaction:
    """Base transaction type."""
    tx_type: str  # "SCRIPTURE", "TRANSFER", "COINBASE"
    data: Dict[str, Any]
    timestamp: int
    signature: Optional[Dict] = None
    
    def hash(self) -> str:
        """Transaction hash."""
        tx_data = {
            'type': self.tx_type,
            'data': self.data,
            'timestamp': self.timestamp
        }
        return hashlib.sha256(
            json.dumps(tx_data, sort_keys=True).encode()
        ).hexdigest()[:32]


@dataclass  
class ScriptureTransaction(Transaction):
    """Scripture anchoring transaction."""
    book: str = ""
    chapter: int = 0
    verse: int = 0
    text_hash: str = ""  # SHA256 of UTF-8 text
    version: str = ""     # e.g., "KJV", "HEBREW_MASORETIC"
    witnesses: List[Dict] = None
    
    def __post_init__(self):
        self.tx_type = "SCRIPTURE"
        if self.witnesses is None:
            self.witnesses = []
    
    def is_valid(self) -> bool:
        """Validate scripture transaction has proper authority signatures."""
        return ScriptureAuthority.verify_multi_sig({
            'text_hash': self.text_hash,
            'witnesses': self.witnesses
        }, CONSENSUS['min_witnesses'])


@dataclass
class Block:
    """
    Blockchain block with E8-enhanced hashing.
    """
    # Header
    version: int = 1
    prev_hash: str = "0" * 64
    merkle_root: str = ""
    timestamp: int = 0
    difficulty: int = 24
    nonce: int = 0
    
    # Body
    transactions: List[Transaction] = None
    
    # Cache
    _hash: str = ""
    _e8_lattice: Optional[E8Lattice] = None
    
    def __post_init__(self):
        if self.transactions is None:
            self.transactions = []
        if self.timestamp == 0:
            self.timestamp = int(time.time())
        self._e8_lattice = E8Lattice()
    
    def compute_merkle_root(self) -> str:
        """Compute merkle root of transactions."""
        if not self.transactions:
            return "0" * 64
        
        hashes = [tx.hash() for tx in self.transactions]
        
        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])  # Duplicate last if odd
            
            new_level = []
            for i in range(0, len(hashes), 2):
                combined = hashes[i] + hashes[i+1]
                new_hash = hashlib.sha256(combined.encode()).hexdigest()[:32]
                new_level.append(new_hash)
            
            hashes = new_level
        
        return hashes[0]
    
    def hash_header(self) -> str:
        """
        Compute block hash with E8 enhancement.
        
        If e8_mining enabled, applies Weyl transformations
        to add quantum-resistant mixing.
        """
        # Standard header hash
        header_data = {
            'version': self.version,
            'prev_hash': self.prev_hash,
            'merkle_root': self.merkle_root or self.compute_merkle_root(),
            'timestamp': self.timestamp,
            'difficulty': self.difficulty,
            'nonce': self.nonce
        }
        
        header_bytes = json.dumps(header_data, sort_keys=True).encode()
        base_hash = hashlib.sha256(header_bytes).digest()
        
        if CONSENSUS['e8_mining']:
            # E8 enhancement: apply Weyl transformations
            point = self._e8_lattice.hash_to_point(base_hash)
            transformed = self._e8_lattice.weyl_transform(
                point, 
                self.nonce
            )
            
            # Hash the transformed point
            final = hashlib.sha256(transformed.tobytes()).digest()
            return final.hex()
        else:
            return base_hash.hex()
    
    def hash(self) -> str:
        """Get or compute block hash."""
        if not self._hash:
            self._hash = self.hash_header()
        return self._hash
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'header': {
                'version': self.version,
                'prev_hash': self.prev_hash,
                'merkle_root': self.merkle_root,
                'timestamp': self.timestamp,
                'difficulty': self.difficulty,
                'nonce': self.nonce,
                'hash': self.hash()
            },
            'transactions': [
                {
                    'type': tx.tx_type,
                    'data': tx.data,
                    'hash': tx.hash(),
                    'signature': tx.signature
                } for tx in self.transactions
            ]
        }
    
    def size(self) -> int:
        """Estimate block size in bytes."""
        return len(json.dumps(self.to_dict()).encode())


class Blockchain:
    """
    Core blockchain with mobile-optimized validation.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.chain: List[Block] = []
        self.utxo_set: Dict[str, Any] = {}  # Simplified UTXO
        self.mempool: List[Transaction] = []
        self.e8 = E8Lattice()
        
        # Load or create genesis
        if not self.chain:
            self._create_genesis()
    
    def _create_genesis(self):
        """Create genesis block with Genesis 1:1."""
        print("⛏️ Mining genesis block...")
        
        # Genesis scripture anchor
        genesis_scripture = ScriptureTransaction(
            book="genesis",
            chapter=1,
            verse=1,
            text_hash=hashlib.sha256(
                "In the beginning God created the heaven and the earth"
                .encode('utf-8')
            ).hexdigest(),
            version="KJV",
            witnesses=[],  # No witnesses for genesis
            timestamp=int(time.time()),
            data={}
        )
        
        genesis = Block(
            version=1,
            prev_hash="0" * 64,
            transactions=[genesis_scripture],
            timestamp=1609459200,  # Jan 1, 2021
            difficulty=CONSENSUS['difficulty']
        )
        
        # Mine genesis
        self.mine_block(genesis)
        self.chain.append(genesis)
        
        print(f"✅ Genesis mined: {genesis.hash()[:20]}...")
    
    def mine_block(self, block: Block, max_iterations: int = 1_000_000) -> bool:
        """
        Mine block with mobile-optimized difficulty.
        
        Yields periodically to allow UI updates.
        """
        target = 2 ** (256 - block.difficulty)
        
        for nonce in range(max_iterations):
            block.nonce = nonce
            hash_int = int(block.hash(), 16)
            
            if hash_int < target:
                return True
            
            # Mobile optimization: yield every 1000 iterations
            if nonce % 1000 == 0 and nonce > 0:
                # In async context, would yield control here
                pass
        
        return False  # Failed to find solution
    
    def validate_block(self, block: Block, prev_block: Optional[Block] = None) -> bool:
        """
        Validate block against consensus rules.
        """
        if prev_block is None:
            prev_block = self.chain[-1] if self.chain else None
        
        # Check links to previous
        if prev_block and block.prev_hash != prev_block.hash():
            print("❌ Invalid previous hash")
            return False
        
        # Check timestamp (must be after prev, not too far in future)
        if prev_block:
            if block.timestamp <= prev_block.timestamp:
                print("❌ Timestamp too old")
                return False
        
        # Check difficulty
        if block.difficulty < self.get_next_difficulty():
            print("❌ Difficulty too low")
            return False
        
        # Check proof of work
        target = 2 ** (256 - block.difficulty)
        if int(block.hash(), 16) >= target:
            print("❌ Invalid PoW")
            return False
        
        # Check size
        if block.size() > CONSENSUS['block_size']:
            print("❌ Block too large")
            return False
        
        # Check transaction count
        if len(block.transactions) > CONSENSUS['max_tx']:
            print("❌ Too many transactions")
            return False
        
        # Validate transactions
        scripture_count = 0
        for tx in block.transactions:
            if isinstance(tx, ScriptureTransaction):
                scripture_count += 1
                if not tx.is_valid() and tx.book != "genesis":
                    print(f"❌ Invalid scripture: {tx.book} {tx.chapter}:{tx.verse}")
                    return False
        
        if scripture_count > CONSENSUS['max_scripture_tx']:
            print("❌ Too many scripture anchors")
            return False
        
        return True
    
    def add_block(self, block: Block) -> bool:
        """Add validated block to chain."""
        if self.validate_block(block):
            self.chain.append(block)
            return True
        return False
    
    def get_next_difficulty(self) -> int:
        """
        Calculate next difficulty based on block time.
        Retargets every retarget_interval blocks.
        """
        if len(self.chain) < 2:
            return CONSENSUS['difficulty']
        
        if len(self.chain) % CONSENSUS['retarget_interval'] != 0:
            return self.chain[-1].difficulty
        
        # Retarget
        last_retarget = self.chain[-CONSENSUS['retarget_interval']]
        actual_time = self.chain[-1].timestamp - last_retarget.timestamp
        expected_time = CONSENSUS['retarget_interval'] * CONSENSUS['block_time']
        
        # Difficulty adjustment (bounded)
        ratio = actual_time / expected_time
        new_diff = int(self.chain[-1].difficulty * ratio)
        
        # Clamp between 16 and 32 for mobile
        return max(16, min(32, new_diff))
    
    def get_chain_stats(self) -> dict:
        """Get blockchain statistics."""
        return {
            'blocks': len(self.chain),
            'difficulty': self.chain[-1].difficulty if self.chain else 0,
            'total_scripture_anchors': sum(
                1 for b in self.chain
                for tx in b.transactions
                if isinstance(tx, ScriptureTransaction)
            ),
            'chain_work': sum(b.difficulty for b in self.chain),
        }


# Demo
if __name__ == "__main__":
    print("⛓️ Chain-Core Blockchain")
    print("=" * 40)
    
    # Create blockchain
    chain = Blockchain()
    
    print(f"\n📊 Chain stats: {chain.get_chain_stats()}")
    
    # Mine another block
    print("\n⛏️ Mining block 2...")
    new_block = Block(
        prev_hash=chain.chain[-1].hash(),
        transactions=[],
        difficulty=chain.get_next_difficulty()
    )
    
    if chain.mine_block(new_block, max_iterations=100_000):
        chain.add_block(new_block)
        print(f"✅ Mined: {new_block.hash()[:20]}...")
    else:
        print("❌ Mining failed (difficulty too high for demo)")
    
    print(f"\n📊 Final stats: {chain.get_chain_stats()}")
