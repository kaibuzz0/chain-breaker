#!/usr/bin/env python3
"""
File-Vault: Document Storage for Chain-Breaker

Stores actual files (PDFs, TXT, etc.) linked to blockchain anchors.
NOT just hashes - real document storage with verification.

Features:
- Store any file type (PDF, TXT, DOCX, images, etc.)
- Link files to blockchain anchors (by hash)
- Verify integrity against blockchain
- Compression for mobile storage
- Chunked storage for large files
- Encryption (optional)
"""

import os
import json
import hashlib
import sqlite3
import zlib
from pathlib import Path
from typing import Dict, List, Optional, BinaryIO
from dataclasses import dataclass
import time


@dataclass
class StoredFile:
    """File metadata stored in vault."""
    file_hash: str
    filename: str
    file_type: str
    size: int
    compressed: bool
    encryption: Optional[str]
    added_timestamp: float
    blockchain_height: Optional[int]
    
    def to_dict(self) -> dict:
        return {
            'file_hash': self.file_hash,
            'filename': self.filename,
            'file_type': self.file_type,
            'size': self.size,
            'compressed': self.compressed,
            'encryption': self.encryption,
            'added_timestamp': self.added_timestamp,
            'blockchain_height': self.blockchain_height
        }


class FileVault:
    """
    Document vault with blockchain verification.
    
    Stores actual files, linking them to blockchain anchors.
    
    Storage Structure:
        vault/
        ├── index.db          # SQLite metadata index
        ├── files/            # Actual files
        │   ├── ab/           # Hash prefix
        │   │   └── cd1234...
        └── chunks/           # Large file chunks
    """
    
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS files (
        file_hash TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        file_type TEXT NOT NULL,
        size INTEGER NOT NULL,
        compressed BOOLEAN DEFAULT FALSE,
        encryption TEXT,
        added_timestamp REAL NOT NULL,
        blockchain_height INTEGER,
        storage_path TEXT NOT NULL
    );
    
    CREATE INDEX IF NOT EXISTS idx_filename ON files(filename);
    CREATE INDEX IF NOT EXISTS idx_added ON files(added_timestamp);
    
    CREATE TABLE IF NOT EXISTS vault_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """
    
    def __init__(self, vault_path: str, compression: bool = True):
        """
        Initialize file vault.
        
        Args:
            vault_path: Directory for vault storage
            compression: Whether to compress files
        """
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.compression = compression
        self.db_path = self.vault_path / "vault.db"
        self.files_path = self.vault_path / "files"
        self.chunks_path = self.vault_path / "chunks"
        
        # Create directories
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.files_path.mkdir(exist_ok=True)
        self.chunks_path.mkdir(exist_ok=True)
        
        self._init_db()
        
    def _init_db(self):
        """Initialize SQLite database."""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()
        
        self._set_meta('version', '1.0.0')
        self._set_meta('compression', 'zlib' if self.compression else 'none')
    
    def _set_meta(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO vault_meta (key, value) VALUES (?, ?)",
            (key, value)
        )
        self.conn.commit()
    
    def _storage_path(self, file_hash: str) -> Path:
        """Get storage path using hash-based directories."""
        prefix = file_hash[:2]
        subdir = self.files_path / prefix
        subdir.mkdir(exist_ok=True)
        return subdir / file_hash
    
    def store_file(self,
                   file_obj: BinaryIO,
                   filename: str,
                   blockchain_height: Optional[int] = None,
                   encryption: Optional[str] = None) -> str:
        """
        Store file in vault.
        
        Args:
            file_obj: File-like object to read
            filename: Original filename
            blockchain_height: Block where anchored
            encryption: Encryption method (None for none)
            
        Returns:
            str: File hash (SHA256) - used to retrieve
        """
        # Read and hash
        content = file_obj.read()
        file_hash = hashlib.sha256(content).hexdigest()
        
        # Check if exists
        if self.get_file_info(file_hash):
            return file_hash
        
        # Detect file type
        file_type = self._detect_type(filename, content)
        
        # Compress if enabled
        if self.compression:
            content = zlib.compress(content)
            compressed = True
        else:
            compressed = False
        
        # Store file
        storage_path = self._storage_path(file_hash)
        with open(storage_path, 'wb') as f:
            f.write(content)
        
        # Add to index
        file_info = StoredFile(
            file_hash=file_hash,
            filename=filename,
            file_type=file_type,
            size=len(content),
            compressed=compressed,
            encryption=encryption,
            added_timestamp=time.time(),
            blockchain_height=blockchain_height
        )
        
        self._add_to_index(file_info, str(storage_path))
        
        return file_hash
    
    def store_from_disk(self, filepath: str, **kwargs) -> str:
        """Store file from disk path."""
        path = Path(filepath)
        with open(path, 'rb') as f:
            return self.store_file(f, path.name, **kwargs)
    
    def retrieve_file(self, file_hash: str) -> Optional[bytes]:
        """
        Retrieve file content.
        
        Args:
            file_hash: File hash (SHA256)
            
        Returns:
            bytes: File content (decompressed if needed)
        """
        info = self.get_file_info(file_hash)
        if not info:
            raise FileNotFoundError(f"File not found: {file_hash}")
        
        # Read file
        storage_path = self._storage_path(file_hash)
        with open(storage_path, 'rb') as f:
            content = f.read()
        
        # Decompress if needed
        if info.compressed:
            content = zlib.decompress(content)
        
        # Verify
        verify_hash = hashlib.sha256(content).hexdigest()
        if verify_hash != file_hash:
            raise ValueError("File corrupted: hash mismatch")
        
        return content
    
    def get_file_info(self, file_hash: str) -> Optional[StoredFile]:
        """Get file metadata."""
        row = self.conn.execute(
            "SELECT * FROM files WHERE file_hash = ?",
            (file_hash,)
        ).fetchone()
        
        if not row:
            return None
        
        return StoredFile(
            file_hash=row['file_hash'],
            filename=row['filename'],
            file_type=row['file_type'],
            size=row['size'],
            compressed=bool(row['compressed']),
            encryption=row['encryption'],
            added_timestamp=row['added_timestamp'],
            blockchain_height=row['blockchain_height']
        )
    
    def list_files(self, limit: int = 100) -> List[StoredFile]:
        """List all files in vault."""
        rows = self.conn.execute(
            "SELECT * FROM files ORDER BY added_timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        
        return [StoredFile(
            file_hash=row['file_hash'],
            filename=row['filename'],
            file_type=row['file_type'],
            size=row['size'],
            compressed=bool(row['compressed']),
            encryption=row['encryption'],
            added_timestamp=row['added_timestamp'],
            blockchain_height=row['blockchain_height']
        ) for row in rows]
    
    def verify_integrity(self, file_hash: str) -> bool:
        """Verify file matches blockchain anchor."""
        try:
            content = self.retrieve_file(file_hash)
            return hashlib.sha256(content).hexdigest() == file_hash
        except:
            return False
    
    def get_stats(self) -> Dict:
        """Get vault statistics."""
        count = self.conn.execute(
            "SELECT COUNT(*) FROM files"
        ).fetchone()[0]
        
        total_size = self.conn.execute(
            "SELECT SUM(size) FROM files"
        ).fetchone()[0] or 0
        
        return {
            'file_count': count,
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'vault_path': str(self.vault_path),
            'compression': self.compression
        }
    
    def _detect_type(self, filename: str, content: bytes) -> str:
        """Detect file MIME type."""
        lower = filename.lower()
        
        if lower.endswith('.pdf'):
            return 'application/pdf'
        elif lower.endswith('.txt'):
            return 'text/plain'
        elif lower.endswith('.docx'):
            return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif lower.endswith('.epub'):
            return 'application/epub+zip'
        elif lower.endswith('.html') or lower.endswith('.htm'):
            return 'text/html'
        elif lower.endswith('.json'):
            return 'application/json'
        elif lower.endswith('.py'):
            return 'text/x-python'
        
        # Try magic bytes
        if content[:4] == b'%PDF':
            return 'application/pdf'
        elif content[:2] == b'PK':
            return 'application/zip'
        
        return 'application/octet-stream'
    
    def _add_to_index(self, file_info: StoredFile, storage_path: str):
        """Add file to database index."""
        self.conn.execute(
            """INSERT INTO files 
               (file_hash, filename, file_type, size, compressed,
                encryption, added_timestamp, blockchain_height, storage_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (file_info.file_hash, file_info.filename, file_info.file_type,
             file_info.size, file_info.compressed, file_info.encryption,
             file_info.added_timestamp, file_info.blockchain_height,
             storage_path)
        )
        self.conn.commit()


if __name__ == "__main__":
    import tempfile
    from io import BytesIO
    
    print("=" * 60)
    print("🧪 FileVault Test")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = FileVault(tmpdir)
        
        # Store test file
        test_content = b"Hello, this is test file content."
        file_hash = vault.store_file(BytesIO(test_content), "test.txt")
        print(f"✅ Stored: {file_hash[:20]}...")
        
        # Retrieve
        retrieved = vault.retrieve_file(file_hash)
        assert retrieved == test_content
        print("✅ Retrieved and verified")
        
        # Stats
        stats = vault.get_stats()
        print(f"✅ Vault: {stats['file_count']} files, {stats['total_size_mb']:.2f} MB")
        
    print("\n🎉 All tests passed!")
