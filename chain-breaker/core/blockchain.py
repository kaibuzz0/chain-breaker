"""
Chain-Breaker Blockchain Module
================================

Full blockchain implementation with E8-enhanced hashing,
SQLite persistence, and mobile-optimized mining.
"""

from typing import List, Optional, Dict, Any
import time
import sqlite3
import threading
from dataclasses import dataclass

from .block import Block, BlockValidator

# Import consensus
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from chain_breaker.consensus.pow import PoWMiner
from chain_breaker.crypto.e8_hash import E8BlockHasher, DifficultyCalculator


@dataclass
class ChainConfig:
    """Blockchain configuration."""
    difficulty: int = 100
    target_block_time: int = 300  # 5 minutes
    db_path: str = "blockchain.db"


class Blockchain:
    """
    Chain-Breaker blockchain with E8-enhanced security.
    
    Features:
    - E8 quantum-resistant hashing
    - PoW mining with difficulty adjustment
    - SQLite persistence
    - Thread-safe operations
    """
    
    def __init__(self, config: ChainConfig = None):
        self.config = config or ChainConfig()
        self.chain: List[Block] = []
        self.db_path = self.config.db_path
        self.lock = threading.RLock()
        self.miner = PoWMiner()
        self.hasher = E8BlockHasher()
        self.difficulty_calc = DifficultyCalculator()
        
        # Initialize database
        self._init_db()
        
        # Load existing chain or create genesis
        if not self._load_from_db():
            self._create_genesis()
    
    def _init_db(self):
        """Initialize SQLite database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                index INTEGER PRIMARY KEY,
                timestamp REAL,
                data TEXT,
                previous_hash TEXT,
                hash TEXT,
                nonce INTEGER,
                difficulty INTEGER,
                merkle_root TEXT
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_blocks_prev_hash 
            ON blocks(previous_hash)
        """)
        
        conn.commit()
        conn.close()
    
    def _load_from_db(self) -> bool:
        """Load chain from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM blocks")
        count = cursor.fetchone()[0]
        
        if count == 0:
            conn.close()
            return False
        
        cursor.execute("SELECT * FROM blocks ORDER BY index")
        rows = cursor.fetchall()
        
        for row in rows:
            block = Block(
                index=row[0],
                timestamp=row[1],
                data=row[2],
                previous_hash=row[3],
                hash=row[4],
                nonce=row[5],
                difficulty=row[6],
                merkle_root=row[7]
            )
            self.chain.append(block)
        
        conn.close()
        return True
    
    def _create_genesis(self):
        """Create genesis block."""
        genesis = Block(
            index=0,
            timestamp=time.time(),
            data="Genesis: In the beginning was the Word",
            previous_hash="0" * 64,
            difficulty=self.config.difficulty
        )
        genesis.compute_hash()
        
        with self.lock:
            self.chain.append(genesis)
            self._save_block(genesis)
    
    def _save_block(self, block: Block):
        """Save block to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO blocks VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            block.index, block.timestamp, block.data,
            block.previous_hash, block.hash, block.nonce,
            block.difficulty, block.merkle_root
        ))
        
        conn.commit()
        conn.close()
    
    def add_block(self, data: str, mine: bool = True, max_nonce: int = 100000) -> Optional[Block]:
        """
        Add a new block to the chain.
        
        Args:
            data: Block data/payload
            mine: Whether to mine the block (find valid nonce)
            max_nonce: Maximum nonce to try
            
        Returns:
            The new block, or None if mining failed
        """
        with self.lock:
            prev_block = self.chain[-1]
            
            block = Block(
                index=len(self.chain),
                timestamp=time.time(),
                data=data,
                previous_hash=prev_block.hash,
                difficulty=self._get_next_difficulty()
            )
            
            if mine:
                nonce, hash_hex = self.miner.mine_block(
                    block.to_dict(),
                    block.difficulty,
                    max_nonce
                )
                
                if nonce is None:
                    return None
                
                block.nonce = nonce
                block.hash = hash_hex
            else:
                block.compute_hash()
            
            self.chain.append(block)
            self._save_block(block)
            
            return block
    
    def _get_next_difficulty(self) -> int:
        """Calculate next block difficulty."""
        if len(self.chain) < 2:
            return self.config.difficulty
        
        # Simple difficulty adjustment (every 10 blocks)
        if len(self.chain) % 10 != 0:
            return self.chain[-1].difficulty
        
        # Calculate based on time difference
        prev_10 = self.chain[-10]
        current = self.chain[-1]
        actual_time = current.timestamp - prev_10.timestamp
        target_time = 10 * self.config.target_block_time
        
        old_diff = current.difficulty
        new_diff = int(old_diff * target_time / max(actual_time, 1))
        
        # Clamp to prevent wild swings
        new_diff = max(1, min(new_diff, old_diff * 4))
        
        return new_diff
    
    def validate_chain(self) -> bool:
        """Validate entire blockchain."""
        with self.lock:
            if len(self.chain) == 0:
                return True
            
            # Validate genesis
            if not self.chain[0].validate():
                return False
            
            # Validate chain continuity
            for i in range(1, len(self.chain)):
                current = self.chain[i]
                previous = self.chain[i-1]
                
                if not BlockValidator.validate_chain_continuity(previous, current):
                    return False
                
                if not current.validate():
                    return False
            
            return True
    
    def get_block_by_index(self, index: int) -> Optional[Block]:
        """Get block by index."""
        if 0 <= index < len(self.chain):
            return self.chain[index]
        return None
    
    def get_block_by_hash(self, hash_hex: str) -> Optional[Block]:
        """Get block by hash."""
        for block in self.chain:
            if block.hash == hash_hex:
                return block
        return None
    
    def get_latest_block(self) -> Block:
        """Get the most recent block."""
        return self.chain[-1]
    
    def get_chain_stats(self) -> Dict[str, Any]:
        """Get blockchain statistics."""
        with self.lock:
            if not self.chain:
                return {"blocks": 0}
            
            total_time = self.chain[-1].timestamp - self.chain[0].timestamp
            avg_block_time = total_time / max(len(self.chain) - 1, 1)
            
            return {
                "blocks": len(self.chain),
                "total_time": total_time,
                "avg_block_time": avg_block_time,
                "current_difficulty": self.chain[-1].difficulty,
                "is_valid": self.validate_chain()
            }
    
    def __len__(self) -> int:
        return len(self.chain)


def create_genesis_block(data: str = "Genesis") -> Block:
    """Utility function to create a genesis block."""
    return Block(
        index=0,
        timestamp=time.time(),
        data=data,
        previous_hash="0" * 64,
        difficulty=1
    )
