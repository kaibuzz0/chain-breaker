#!/usr/bin/env python3
"""
Mobile-DB: SQLite-based blockchain storage for Android/Termux
Optimized for limited storage and battery life.
"""

import sqlite3
import json
import os
import time
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
import threading

from chain_core import Block, Transaction, ScriptureTransaction


class MobileChainDB:
    """
    SQLite-backed blockchain storage with three operating modes.
    
    Modes:
    - ultra_light: Headers only (~50MB), for phones
    - light: Headers + recent blocks + UTXO (~200MB)
    - full: Everything (~2GB), for dedicated nodes
    """
    
    SCHEMA = """
    -- Block headers (always stored)
    CREATE TABLE IF NOT EXISTS headers (
        height INTEGER PRIMARY KEY,
        hash BLOB UNIQUE NOT NULL,
        prev_hash BLOB NOT NULL,
        merkle_root BLOB NOT NULL,
        timestamp INTEGER NOT NULL,
        difficulty INTEGER NOT NULL,
        nonce INTEGER NOT NULL,
        version INTEGER DEFAULT 1,
        size_bytes INTEGER
    );
    
    -- Full block data (prunable based on mode)
    CREATE TABLE IF NOT EXISTS blocks (
        hash BLOB PRIMARY KEY,
        height INTEGER NOT NULL,
        data BLOB NOT NULL,  -- JSON serialized block
        is_prunable BOOLEAN DEFAULT TRUE,
        FOREIGN KEY(height) REFERENCES headers(height)
    );
    
    -- Scripture anchors (always kept - small and valuable)
    CREATE TABLE IF NOT EXISTS scripture_anchors (
        tx_hash BLOB PRIMARY KEY,
        block_hash BLOB NOT NULL,
        height INTEGER NOT NULL,
        book TEXT NOT NULL,
        chapter INTEGER NOT NULL,
        verse INTEGER NOT NULL,
        text_hash TEXT NOT NULL,
        version TEXT NOT NULL,
        witness_count INTEGER DEFAULT 0,
        timestamp INTEGER NOT NULL,
        FOREIGN KEY(block_hash) REFERENCES blocks(hash),
        FOREIGN KEY(height) REFERENCES headers(height)
    );
    
    -- Scripture index for fast lookup
    CREATE INDEX IF NOT EXISTS idx_scripture_ref 
    ON scripture_anchors(book, chapter, verse);
    
    CREATE INDEX IF NOT EXISTS idx_scripture_version
    ON scripture_anchors(version);
    
    -- Peers for P2P
    CREATE TABLE IF NOT EXISTS peers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        address TEXT UNIQUE NOT NULL,
        port INTEGER DEFAULT 8333,
        last_seen INTEGER,
        banned BOOLEAN DEFAULT FALSE,
        ban_reason TEXT
    );
    
    -- Chain metadata
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    
    -- Wallet data (encrypted)
    CREATE TABLE IF NOT EXISTS wallet (
        id INTEGER PRIMARY KEY,
        public_key TEXT UNIQUE,
        encrypted_private BLOB,  -- Hardware encrypted if available
        balance INTEGER DEFAULT 0,
        created_at INTEGER
    );
    """
    
    def __init__(self, path: str, mode: str = "light"):
        self.path = path
        self.mode = mode
        self._local = threading.local()
        self._init_db()
        
    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
    
    def _init_db(self):
        """Initialize database schema."""
        conn = self._get_conn()
        conn.executescript(self.SCHEMA)
        conn.commit()
        
        # Store mode
        self.set_meta('storage_mode', self.mode)
        self.set_meta('initialized_at', str(int(time.time())))
    
    def set_meta(self, key: str, value: str):
        """Set metadata value."""
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()
    
    def get_meta(self, key: str) -> Optional[str]:
        """Get metadata value."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = ?", (key,)
        ).fetchone()
        return row['value'] if row else None
    
    def store_block(self, block: Block, is_prunable: bool = True):
        """
        Store block with mode-aware pruning.
        
        Args:
            block: Block to store
            is_prunable: Can this block be deleted in light modes?
        """
        conn = self._get_conn()
        
        # Always store header
        conn.execute("""
            INSERT OR REPLACE INTO headers 
            (height, hash, prev_hash, merkle_root, timestamp, 
             difficulty, nonce, version, size_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            block.timestamp,  # Use timestamp as height proxy
            bytes.fromhex(block.hash()),
            bytes.fromhex(block.prev_hash),
            bytes.fromhex(block.merkle_root or "0" * 64),
            block.timestamp,
            block.difficulty,
            block.nonce,
            block.version,
            block.size()
        ))
        
        # Store full block data based on mode
        should_store_full = (
            self.mode == "full" or 
            (self.mode == "light" and not is_prunable) or
            len(block.transactions) == 0  # Genesis always kept
        )
        
        if should_store_full:
            block_data = json.dumps(block.to_dict()).encode()
            conn.execute("""
                INSERT OR REPLACE INTO blocks (hash, height, data, is_prunable)
                VALUES (?, ?, ?, ?)
            """, (
                bytes.fromhex(block.hash()),
                block.timestamp,
                block_data,
                is_prunable
            ))
            
            # Store scripture anchors
            for tx in block.transactions:
                if isinstance(tx, ScriptureTransaction):
                    conn.execute("""
                        INSERT OR REPLACE INTO scripture_anchors
                        (tx_hash, block_hash, height, book, chapter, verse,
                         text_hash, version, witness_count, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        bytes.fromhex(tx.hash()),
                        bytes.fromhex(block.hash()),
                        block.timestamp,
                        tx.book,
                        tx.chapter,
                        tx.verse,
                        tx.text_hash,
                        tx.version,
                        len(tx.witnesses) if tx.witnesses else 0,
                        tx.timestamp
                    ))
        
        conn.commit()
    
    def get_block(self, block_hash: str) -> Optional[Block]:
        """Retrieve block by hash."""
        conn = self._get_conn()
        
        # Try full block first
        row = conn.execute(
            "SELECT data FROM blocks WHERE hash = ?",
            (bytes.fromhex(block_hash),)
        ).fetchone()
        
        if row:
            # Reconstruct from stored data
            block_dict = json.loads(row['data'])
            return self._dict_to_block(block_dict)
        
        # Fall back to header-only
        row = conn.execute(
            "SELECT * FROM headers WHERE hash = ?",
            (bytes.fromhex(block_hash),)
        ).fetchone()
        
        if row:
            return Block(
                version=row['version'],
                prev_hash=row['prev_hash'].hex(),
                merkle_root=row['merkle_root'].hex(),
                timestamp=row['timestamp'],
                difficulty=row['difficulty'],
                nonce=row['nonce'],
                transactions=[]  # Not stored in light mode
            )
        
        return None
    
    def get_header(self, height: int) -> Optional[Dict]:
        """Get block header by height (fast)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM headers WHERE height = ?",
            (height,)
        ).fetchone()
        
        if row:
            return {
                'height': row['height'],
                'hash': row['hash'].hex(),
                'prev_hash': row['prev_hash'].hex(),
                'merkle_root': row['merkle_root'].hex(),
                'timestamp': row['timestamp'],
                'difficulty': row['difficulty'],
                'nonce': row['nonce']
            }
        return None
    
    def get_tip(self) -> Optional[Dict]:
        """Get chain tip (latest block header)."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM headers ORDER BY height DESC LIMIT 1"
        ).fetchone()
        
        if row:
            return {
                'height': row['height'],
                'hash': row['hash'].hex(),
                'difficulty': row['difficulty']
            }
        return None
    
    def get_scripture(self, book: str, chapter: int, verse: int,
                     version: Optional[str] = None) -> List[Dict]:
        """
        Lookup scripture anchor(s) by reference.
        Returns all versions if version not specified.
        """
        conn = self._get_conn()
        
        if version:
            rows = conn.execute("""
                SELECT * FROM scripture_anchors 
                WHERE book = ? AND chapter = ? AND verse = ? AND version = ?
                ORDER BY height DESC
            """, (book, chapter, verse, version)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM scripture_anchors 
                WHERE book = ? AND chapter = ? AND verse = ?
                ORDER BY version, height DESC
            """, (book, chapter, verse)).fetchall()
        
        return [
            {
                'tx_hash': row['tx_hash'].hex()[:16],
                'block_hash': row['block_hash'].hex()[:16],
                'height': row['height'],
                'version': row['version'],
                'text_hash': row['text_hash'][:16],
                'witness_count': row['witness_count'],
                'timestamp': row['timestamp']
            }
            for row in rows
        ]
    
    def prune_old_blocks(self, keep_blocks: int = 1000):
        """
        Prune old full block data in light/ultra-light modes.
        Keeps headers and scripture anchors always.
        """
        if self.mode == "full":
            return  # Don't prune in full mode
        
        conn = self._get_conn()
        tip = self.get_tip()
        if not tip:
            return
        
        cutoff_height = tip['height'] - keep_blocks
        
        # Delete prunable full blocks older than cutoff
        conn.execute("""
            DELETE FROM blocks 
            WHERE height < ? AND is_prunable = TRUE
        """, (cutoff_height,))
        
        pruned = conn.total_changes
        conn.commit()
        
        print(f"Pruned {pruned} old blocks (mode: {self.mode})")
    
    def get_db_size(self) -> int:
        """Get database file size in bytes."""
        return os.path.getsize(self.path)
    
    def get_stats(self) -> Dict:
        """Get database statistics."""
        conn = self._get_conn()
        
        stats = {
            'mode': self.mode,
            'file_size_mb': self.get_db_size() / (1024 * 1024),
            'headers': conn.execute(
                "SELECT COUNT(*) FROM headers"
            ).fetchone()[0],
            'full_blocks': conn.execute(
                "SELECT COUNT(*) FROM blocks"
            ).fetchone()[0],
            'scripture_anchors': conn.execute(
                "SELECT COUNT(*) FROM scripture_anchors"
            ).fetchone()[0],
            'peers': conn.execute(
                "SELECT COUNT(*) FROM peers WHERE banned = FALSE"
            ).fetchone()[0]
        }
        
        return stats
    
    def _dict_to_block(self, block_dict: Dict) -> Block:
        """Reconstruct Block from dictionary."""
        header = block_dict['header']
        
        transactions = []
        for tx_data in block_dict.get('transactions', []):
            if tx_data['type'] == 'SCRIPTURE':
                tx = ScriptureTransaction(
                    book=tx_data.get('book', ''),
                    chapter=tx_data.get('chapter', 0),
                    verse=tx_data.get('verse', 0),
                    text_hash=tx_data.get('text_hash', ''),
                    version=tx_data.get('version', ''),
                    timestamp=tx_data.get('timestamp', 0),
                    data=tx_data.get('data', {})
                )
                transactions.append(tx)
        
        return Block(
            version=header['version'],
            prev_hash=header['prev_hash'],
            merkle_root=header['merkle_root'],
            timestamp=header['timestamp'],
            difficulty=header['difficulty'],
            nonce=header['nonce'],
            transactions=transactions
        )


class BatteryAwareDB:
    """
    Wrapper that respects battery and data constraints.
    """
    
    def __init__(self, db: MobileChainDB):
        self.db = db
        self.sync_enabled = True
        self.prune_threshold = 100 * 1024 * 1024  # 100MB
        
    def should_prune(self) -> bool:
        """Check if we should prune to save space."""
        return self.db.get_db_size() > self.prune_threshold
    
    def optimize_for_battery(self, battery_level: int, is_charging: bool):
        """
        Adjust sync behavior based on battery state.
        
        Args:
            battery_level: 0-100
            is_charging: Whether plugged in
        """
        if battery_level < 20 and not is_charging:
            self.sync_enabled = False
            print("🔋 Battery low - sync paused")
        elif is_charging:
            self.sync_enabled = True
            print("⚡ Charging - sync resumed")


# Demo
if __name__ == "__main__":
    print("📱 Mobile Database (SQLite)")
    print("=" * 40)
    
    # Create test database
    db = MobileChainDB("test_chain.db", mode="light")
    
    print(f"\n📊 Initial stats: {db.get_stats()}")
    
    # Store a mock block
    from chain_core import Block
    test_block = Block(
        prev_hash="0" * 64,
        timestamp=int(time.time()),
        difficulty=24
    )
    
    db.store_block(test_block)
    print(f"\n📊 After block: {db.get_stats()}")
    
    # Lookup
    print("\n🔍 Looking up scripture...")
    results = db.get_scripture("genesis", 1, 1)
    print(f"   Found {len(results)} anchors")
    
    print("\n✅ Mobile DB ready")
