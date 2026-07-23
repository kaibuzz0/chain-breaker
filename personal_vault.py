#!/usr/bin/env python3
"""
Personal Bible Vault - Private Collection Storage

For preserving YOUR collected Bible books and documents.
NOT a public system - permissioned access only.

Purpose:
- Store your curated Bible collection from local disk
- Anchor file hashes to blockchain for eternal proof of existence
- Compression for storage efficiency
- Personal index (your organization)

Security:
- Only authorized keys can add files
- Read-only for others (if shared)
- Blockchain proves documents existed at timestamp
"""

import os
import json
import hashlib
import sqlite3
import zlib
from pathlib import Path
from typing import Dict, List, Optional, BinaryIO, Set
from dataclasses import dataclass
import time


@dataclass
class VaultedDocument:
    """Document in your personal vault."""
    doc_hash: str          # SHA256 of content
    filename: str          # Original filename
    file_path: str         # Original path (for reference)
    file_type: str         # MIME type
    size_bytes: int        # Original size
    stored_size: int       # Compressed size
    added_date: float      # Unix timestamp
    blockchain_height: Optional[int]  # When anchored
    title: Optional[str]   # Your title for it
    notes: Optional[str]   # Your personal notes


class PersonalBibleVault:
    """
    YOUR personal Bible document vault.
    
    Store your collected Bible books, anchor to blockchain.
    Permissioned - only you can add documents.
    
    Usage:
        vault = PersonalBibleVault("~/bible-vault", your_private_key)
        
        # Add your collection
        vault.import_directory("D:/full bible/keep")
        
        # Anchor to blockchain
        for doc_hash in vault.pending_anchors():
            blockchain.anchor_document(doc_hash)
    """
    
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS my_documents (
        doc_hash TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        file_path TEXT,
        file_type TEXT,
        size_bytes INTEGER,
        stored_size INTEGER,
        added_date REAL,
        blockchain_height INTEGER,
        title TEXT,
        notes TEXT
    );
    
    CREATE INDEX IF NOT EXISTS idx_added ON my_documents(added_date);
    CREATE INDEX IF NOT EXISTS idx_filename ON my_documents(filename);
    
    -- Authorized keys (who can add files)
    CREATE TABLE IF NOT EXISTS authorized_keys (
        public_key TEXT PRIMARY KEY,
        added_date REAL,
        notes TEXT
    );
    
    CREATE TABLE IF NOT EXISTS vault_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """
    
    def __init__(self, vault_path: str, owner_public_key: Optional[str] = None):
        """
        Initialize YOUR vault.
        
        Args:
            vault_path: Where to store vault
            owner_public_key: Your key (only this can add files)
        """
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.db_path = self.vault_path / "my-vault.db"
        self.docs_path = self.vault_path / "documents"
        
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.docs_path.mkdir(exist_ok=True)
        
        self._init_db()
        
        # Set owner
        if owner_public_key:
            self._add_authorized_key(owner_public_key, "Owner")
            self.owner_key = owner_public_key
        
        print(f"🔐 Personal Vault: {self.vault_path}")
        print(f"   Documents: {self.get_document_count()} files stored")
        
    def _init_db(self):
        """Setup database."""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()
        
    def _add_authorized_key(self, public_key: str, notes: str = ""):
        """Add authorized key (only called during init)."""
        self.conn.execute(
            """INSERT OR IGNORE INTO authorized_keys 
               (public_key, added_date, notes) VALUES (?, ?, ?)""",
            (public_key, time.time(), notes)
        )
        self.conn.commit()
        
    def _is_authorized(self, public_key: str) -> bool:
        """Check if key can add documents."""
        row = self.conn.execute(
            "SELECT 1 FROM authorized_keys WHERE public_key = ?",
            (public_key,)
        ).fetchone()
        return row is not None
    
    def add_document(self, 
                     filepath: str,
                     public_key: str,
                     title: Optional[str] = None,
                     notes: Optional[str] = None) -> str:
        """
        Add document to YOUR vault.
        
        Args:
            filepath: Path to file
            public_key: Your authorized key
            title: Your title for this document
            notes: Your notes
            
        Returns:
            str: Document hash
            
        Raises:
            PermissionError: If public_key not authorized
        """
        if not self._is_authorized(public_key):
            raise PermissionError("Not authorized to add documents")
        
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        
        # Read and hash
        with open(path, 'rb') as f:
            content = f.read()
        
        doc_hash = hashlib.sha256(content).hexdigest()
        
        # Check if already stored
        if self.get_document(doc_hash):
            print(f"   Already in vault: {path.name}")
            return doc_hash
        
        # Compress
        compressed = zlib.compress(content)
        
        # Store
        storage_path = self._storage_path(doc_hash)
        with open(storage_path, 'wb') as f:
            f.write(compressed)
        
        # Index
        doc = VaultedDocument(
            doc_hash=doc_hash,
            filename=path.name,
            file_path=str(path),
            file_type=self._detect_type(path.name, content),
            size_bytes=len(content),
            stored_size=len(compressed),
            added_date=time.time(),
            blockchain_height=None,  # Not anchored yet
            title=title or path.stem,
            notes=notes
        )
        
        self._index_document(doc)
        
        print(f"✅ Added: {path.name}")
        print(f"   Hash: {doc_hash[:32]}...")
        print(f"   Size: {len(content):,} bytes → {len(compressed):,} compressed")
        
        return doc_hash
    
    def import_directory(self, 
                        directory: str,
                        public_key: str,
                        extensions: Optional[Set[str]] = None) -> List[str]:
        """
        Import YOUR collection from directory.
        
        Args:
            directory: Path to your Bible collection (e.g., "D:/full bible/keep")
            public_key: Your authorized key
            extensions: File types to import (default: .pdf, .txt, .epub)
            
        Returns:
            List[str]: Hashes of imported documents
        """
        if not self._is_authorized(public_key):
            raise PermissionError("Not authorized")
        
        if extensions is None:
            extensions = {'.pdf', '.txt', '.epub', '.docx', '.html'}
        
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        print(f"\n📁 Importing from: {directory}")
        print(f"   Looking for: {extensions}")
        print()
        
        imported = []
        
        for ext in extensions:
            for filepath in dir_path.rglob(f"*{ext}"):
                try:
                    doc_hash = self.add_document(
                        str(filepath),
                        public_key,
                        title=filepath.stem
                    )
                    imported.append(doc_hash)
                except Exception as e:
                    print(f"   ⚠️  Failed {filepath.name}: {e}")
        
        print(f"\n✅ Imported {len(imported)} documents")
        return imported
    
    def get_document(self, doc_hash: str) -> Optional[VaultedDocument]:
        """Get document info."""
        row = self.conn.execute(
            "SELECT * FROM my_documents WHERE doc_hash = ?",
            (doc_hash,)
        ).fetchone()
        
        if not row:
            return None
        
        return VaultedDocument(
            doc_hash=row['doc_hash'],
            filename=row['filename'],
            file_path=row['file_path'],
            file_type=row['file_type'],
            size_bytes=row['size_bytes'],
            stored_size=row['stored_size'],
            added_date=row['added_date'],
            blockchain_height=row['blockchain_height'],
            title=row['title'],
            notes=row['notes']
        )
    
    def retrieve_content(self, doc_hash: str) -> bytes:
        """Get document content (decompressed)."""
        doc = self.get_document(doc_hash)
        if not doc:
            raise FileNotFoundError(f"Document not found: {doc_hash}")
        
        storage_path = self._storage_path(doc_hash)
        with open(storage_path, 'rb') as f:
            compressed = f.read()
        
        return zlib.decompress(compressed)
    
    def mark_anchored(self, doc_hash: str, blockchain_height: int):
        """Mark document as anchored to blockchain."""
        self.conn.execute(
            "UPDATE my_documents SET blockchain_height = ? WHERE doc_hash = ?",
            (blockchain_height, doc_hash)
        )
        self.conn.commit()
        
    def pending_anchors(self) -> List[str]:
        """Get documents not yet anchored to blockchain."""
        rows = self.conn.execute(
            "SELECT doc_hash FROM my_documents WHERE blockchain_height IS NULL"
        ).fetchall()
        return [row['doc_hash'] for row in rows]
    
    def list_documents(self) -> List[VaultedDocument]:
        """List all your documents."""
        rows = self.conn.execute(
            "SELECT * FROM my_documents ORDER BY added_date DESC"
        ).fetchall()
        
        return [VaultedDocument(
            doc_hash=row['doc_hash'],
            filename=row['filename'],
            file_path=row['file_path'],
            file_type=row['file_type'],
            size_bytes=row['size_bytes'],
            stored_size=row['stored_size'],
            added_date=row['added_date'],
            blockchain_height=row['blockchain_height'],
            title=row['title'],
            notes=row['notes']
        ) for row in rows]
    
    def get_document_count(self) -> int:
        """Count documents in vault."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM my_documents"
        ).fetchone()
        return row[0]
    
    def get_stats(self) -> Dict:
        """Vault statistics."""
        count = self.get_document_count()
        
        total_original = self.conn.execute(
            "SELECT SUM(size_bytes) FROM my_documents"
        ).fetchone()[0] or 0
        
        total_stored = self.conn.execute(
            "SELECT SUM(stored_size) FROM my_documents"
        ).fetchone()[0] or 0
        
        anchored = self.conn.execute(
            "SELECT COUNT(*) FROM my_documents WHERE blockchain_height IS NOT NULL"
        ).fetchone()[0]
        
        return {
            'document_count': count,
            'anchored_count': anchored,
            'pending_anchor': count - anchored,
            'total_original_mb': total_original / (1024 * 1024),
            'total_stored_mb': total_stored / (1024 * 1024),
            'compression_ratio': total_original / total_stored if total_stored > 0 else 1,
            'vault_path': str(self.vault_path)
        }
    
    def _storage_path(self, doc_hash: str) -> Path:
        """Get storage location."""
        prefix = doc_hash[:2]
        subdir = self.docs_path / prefix
        subdir.mkdir(exist_ok=True)
        return subdir / doc_hash
    
    def _detect_type(self, filename: str, content: bytes) -> str:
        """Detect file type."""
        lower = filename.lower()
        
        if lower.endswith('.pdf'):
            return 'application/pdf'
        elif lower.endswith('.txt'):
            return 'text/plain'
        elif lower.endswith('.epub'):
            return 'application/epub+zip'
        elif lower.endswith('.docx'):
            return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif lower.endswith('.html') or lower.endswith('.htm'):
            return 'text/html'
        
        if content[:4] == b'%PDF':
            return 'application/pdf'
        elif content[:2] == b'PK':
            return 'application/zip'
        
        return 'application/octet-stream'
    
    def _index_document(self, doc: VaultedDocument):
        """Add to database."""
        self.conn.execute(
            """INSERT INTO my_documents 
               (doc_hash, filename, file_path, file_type, size_bytes,
                stored_size, added_date, blockchain_height, title, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (doc.doc_hash, doc.filename, doc.file_path, doc.file_type,
             doc.size_bytes, doc.stored_size, doc.added_date,
             doc.blockchain_height, doc.title, doc.notes)
        )
        self.conn.commit()


if __name__ == "__main__":
    import tempfile
    
    print("=" * 60)
    print("🔐 Personal Bible Vault Demo")
    print("=" * 60)
    print()
    
    # Create demo vault
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = PersonalBibleVault(tmpdir, owner_public_key="owner_key_123")
        
        # Simulate adding your files
        print("Simulating import from D:/full bible/keep...")
        print()
        
        # Create test files
        test_dir = Path(tmpdir) / "test-collection"
        test_dir.mkdir()
        
        # Add some test documents
        for i in range(3):
            test_file = test_dir / f"bible_copy_{i+1}.pdf"
            test_file.write_bytes(f"Fake PDF content {i}".encode() * 1000)
        
        # Import
        hashes = vault.import_directory(
            str(test_dir),
            public_key="owner_key_123"
        )
        
        print()
        print("📊 Vault Stats:")
        stats = vault.get_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        print()
        print(f"✅ Vault ready - {len(hashes)} documents imported")
        print("   Next: Anchor to blockchain")
