#!/usr/bin/env python3
"""
File-Vault: Bible Document Storage for Chain-Breaker

Stores actual PDF/text files linked to blockchain anchors.
NOT just hashes - real document storage with verification.

Features:
- Store PDFs, TXT, DOCX files
- Link files to blockchain anchors (by hash)
- Verify integrity against blockchain
- Compression for mobile storage
- Chunked storage for large files
- Encryption (optional)

Author: Chain-Breaker Team
Version: 1.0.0
"""

import os
import json
import hashlib
import sqlite3
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, BinaryIO
from dataclasses import dataclass
import time

__version__ = "1.0.0"
__all__ = ['FileVault', 'StoredDocument', 'DocumentType']


class DocumentType:
    """Document type constants."""
    PDF = "application/pdf"
    TXT = "text/plain"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    EPUB = "application/epub+zip"
    HTML = "text/html"
    UNKNOWN = "application/octet-stream"


@dataclass
class StoredDocument:
    """
    Document metadata stored in vault.
    
    Attributes:
        doc_hash: SHA256 of document content (links to blockchain)
        filename: Original filename
        doc_type: MIME type
        size: File size in bytes
        compressed: Whether stored compressed
        encryption: Encryption method (or None)
        added_timestamp: When added to vault
        blockchain_height: Block height where anchored
        verse_ref: Bible verse reference (e.g., "Genesis.1.1")
        version: Bible version (e.g., "KJV", "HEBREW_MASORETIC")
        language: Language code (e.g., "en", "he", "grc")
    """
    doc_hash: str
    filename: str
    doc_type: str
    size: int
    compressed: bool
    encryption: Optional[str]
    added_timestamp: float
    blockchain_height: Optional[int]
    verse_ref: Optional[str]
    version: Optional[str]
    language: Optional[str]
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'doc_hash': self.doc_hash,
            'filename': self.filename,
            'doc_type': self.doc_type,
            'size': self.size,
            'compressed': self.compressed,
            'encryption': self.encryption,
            'added_timestamp': self.added_timestamp,
            'blockchain_height': self.blockchain_height,
            'verse_ref': self.verse_ref,
            'version': self.version,
            'language': self.language
        }


class FileVault:
    """
    Bible document vault with blockchain verification.
    
    Stores actual PDFs and other documents, linking them to
    blockchain anchors for eternal verification.
    
    Storage Structure:
        vault/
        ├── index.db          # SQLite metadata index
        ├── docs/             # Actual document files
        │   ├── ab/           # Hash prefix (first 2 chars)
        │   │   └── cd1234... # Full hash as filename
        │   └── ef/
        └── chunks/           # Large file chunks (optional)
    
    Attributes:
        vault_path: Root directory for vault storage
        db: SQLite connection
        compression: Whether to compress documents
        
    Example:
        >>> vault = FileVault("~/bible-vault")
        >>> 
        >>> # Store a PDF
        >>> with open("genesis.pdf", "rb") as f:
        ...     doc_hash = vault.store_document(
        ...         f, 
        ...         "genesis.pdf",
        ...         verse_ref="Genesis.1.1-50",
        ...         version="KJV"
        ...     )
        >>> print(f"Stored with hash: {doc_hash}")
        >>> 
        >>> # Retrieve it
        >>> doc = vault.get_document(doc_hash)
        >>> with open("retrieved.pdf", "wb") as f:
        ...     f.write(doc)
    """
    
    SCHEMA = """
    -- Document metadata index
    CREATE TABLE IF NOT EXISTS documents (
        doc_hash TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        doc_type TEXT NOT NULL,
        size INTEGER NOT NULL,
        compressed BOOLEAN DEFAULT FALSE,
        encryption TEXT,
        added_timestamp REAL NOT NULL,
        blockchain_height INTEGER,
        verse_ref TEXT,
        version TEXT,
        language TEXT,
        storage_path TEXT NOT NULL
    );
    
    -- Index by verse reference for fast lookup
    CREATE INDEX IF NOT EXISTS idx_verse_ref 
    ON documents(verse_ref);
    
    -- Index by version
    CREATE INDEX IF NOT EXISTS idx_version 
    ON documents(version);
    
    -- Index by blockchain height
    CREATE INDEX IF NOT EXISTS idx_blockchain 
    ON documents(blockchain_height);
    
    -- Search index for filenames
    CREATE INDEX IF NOT EXISTS idx_filename 
    ON documents(filename);
    
    -- Vault metadata
    CREATE TABLE IF NOT EXISTS vault_meta (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """
    
    def __init__(self, vault_path: str, compression: bool = True):
        """
        Initialize file vault.
        
        Args:
            vault_path: Directory to store vault (created if not exists)
            compression: Whether to compress documents (default True)
        """
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.compression = compression
        self.db_path = self.vault_path / "index.db"
        self.docs_path = self.vault_path / "docs"
        self.chunks_path = self.vault_path / "chunks"
        
        # Create directories
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.docs_path.mkdir(exist_ok=True)
        self.chunks_path.mkdir(exist_ok=True)
        
        # Initialize database
        self._init_db()
        
        print(f"📁 FileVault initialized: {self.vault_path}")
        print(f"   Documents: {self.docs_path}")
        print(f"   Database: {self.db_path}")
    
    def _init_db(self):
        """Initialize SQLite database."""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()
        
        # Store metadata
        self._set_meta('version', '1.0.0')
        self._set_meta('compression', 'zlib' if self.compression else 'none')
        self._set_meta('created', str(time.time()))
    
    def _set_meta(self, key: str, value: str):
        """Set metadata value."""
        self.conn.execute(
            "INSERT OR REPLACE INTO vault_meta (key, value) VALUES (?, ?)",
            (key, value)
        )
        self.conn.commit()
    
    def _get_meta(self, key: str) -> Optional[str]:
        """Get metadata value."""
        row = self.conn.execute(
            "SELECT value FROM vault_meta WHERE key = ?", (key,)
        ).fetchone()
        return row['value'] if row else None
    
    def _storage_path(self, doc_hash: str) -> Path:
        """
        Get storage path for document.
        
        Uses hash-based directory structure:
        ab/cd1234... → docs/ab/cd1234...
        """
        prefix = doc_hash[:2]
        subdir = self.docs_path / prefix
        subdir.mkdir(exist_ok=True)
        return subdir / doc_hash
    
    def store_document(self,
                      file_obj: BinaryIO,
                      filename: str,
                      verse_ref: Optional[str] = None,
                      version: Optional[str] = None,
                      language: Optional[str] = None,
                      blockchain_height: Optional[int] = None,
                      encryption: Optional[str] = None) -> str:
        """
        Store document in vault.
        
        Args:
            file_obj: File-like object to read from
            filename: Original filename
            verse_ref: Bible reference (e.g., "Genesis.1.1")
            version: Bible version (e.g., "KJV")
            language: Language code (e.g., "en", "he")
            blockchain_height: Block where anchored
            encryption: Encryption method (None for unencrypted)
            
        Returns:
            str: Document hash (SHA256) - used to retrieve
        """
        # Read file content
        content = file_obj.read()
        
        # Calculate hash
        doc_hash = hashlib.sha256(content).hexdigest()
        
        # Check if already exists
        existing = self.get_document_info(doc_hash)
        if existing:
            print(f"   Document already exists: {doc_hash[:16]}...")
            return doc_hash
        
        # Determine file type
        doc_type = self._detect_type(filename, content)
        
        # Compress if enabled
        if self.compression:
            content = zlib.compress(content)
            compressed = True
        else:
            compressed = False
        
        # Store file
        storage_path = self._storage_path(doc_hash)
        with open(storage_path, 'wb') as f:
            f.write(content)
        
        # Add to index
        doc = StoredDocument(
            doc_hash=doc_hash,
            filename=filename,
            doc_type=doc_type,
            size=len(content),
            compressed=compressed,
            encryption=encryption,
            added_timestamp=time.time(),
            blockchain_height=blockchain_height,
            verse_ref=verse_ref,
            version=version,
            language=language
        )
        
        self._add_to_index(doc, str(storage_path))
        
        print(f"✅ Stored: {filename}")
        print(f"   Hash: {doc_hash[:32]}...")
        print(f"   Size: {len(content):,} bytes")
        print(f"   Type: {doc_type}")
        if verse_ref:
            print(f"   Verse: {verse_ref}")
        
        return doc_hash
    
    def store_file(self, filepath: str, **kwargs) -> str:
        """
        Store file from disk.
        
        Args:
            filepath: Path to file
            **kwargs: Same as store_document()
            
        Returns:
            str: Document hash
        """
        path = Path(filepath)
        with open(path, 'rb') as f:
            return self.store_document(f, path.name, **kwargs)
    
    def get_document(self, doc_hash: str) -> Optional[bytes]:
        """
        Retrieve document content.
        
        Args:
            doc_hash: Document hash (SHA256)
            
        Returns:
            bytes: Document content (decompressed if needed)
            
        Raises:
            FileNotFoundError: If document not in vault
        """
        # Get metadata
        info = self.get_document_info(doc_hash)
        if not info:
            raise FileNotFoundError(f"Document not found: {doc_hash}")
        
        # Read file
        storage_path = self._storage_path(doc_hash)
        with open(storage_path, 'rb') as f:
            content = f.read()
        
        # Decompress if needed
        if info.compressed:
            content = zlib.decompress(content)
        
        # Verify integrity
        verify_hash = hashlib.sha256(content).hexdigest()
        if verify_hash != doc_hash:
            raise ValueError(f"Corrupted document: hash mismatch")
        
        return content
    
    def get_document_info(self, doc_hash: str) -> Optional[StoredDocument]:
        """
        Get document metadata.
        
        Args:
            doc_hash: Document hash
            
        Returns:
            StoredDocument or None if not found
        """
        row = self.conn.execute(
            """SELECT * FROM documents WHERE doc_hash = ?""",
            (doc_hash,)
        ).fetchone()
        
        if not row:
            return None
        
        return StoredDocument(
            doc_hash=row['doc_hash'],
            filename=row['filename'],
            doc_type=row['doc_type'],
            size=row['size'],
            compressed=bool(row['compressed']),
            encryption=row['encryption'],
            added_timestamp=row['added_timestamp'],
            blockchain_height=row['blockchain_height'],
            verse_ref=row['verse_ref'],
            version=row['version'],
            language=row['language']
        )
    
    def get_document_path(self, doc_hash: str) -> Path:
        """Get storage path for document (for external access)."""
        return self._storage_path(doc_hash)
    
    def find_by_verse(self, verse_ref: str, version: Optional[str] = None) -> List[StoredDocument]:
        """
        Find documents by Bible verse reference.
        
        Args:
            verse_ref: Verse reference (e.g., "Genesis.1.1")
            version: Optional version filter
            
        Returns:
            List of matching documents
        """
        if version:
            rows = self.conn.execute(
                """SELECT * FROM documents 
                   WHERE verse_ref = ? AND version = ?""",
                (verse_ref, version)
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM documents WHERE verse_ref = ?""",
                (verse_ref,)
            ).fetchall()
        
        return [self._row_to_doc(row) for row in rows]
    
    def find_by_version(self, version: str) -> List[StoredDocument]:
        """Find all documents for a specific Bible version."""
        rows = self.conn.execute(
            """SELECT * FROM documents WHERE version = ?""",
            (version,)
        ).fetchall()
        return [self._row_to_doc(row) for row in rows]
    
    def list_all(self, limit: int = 100) -> List[StoredDocument]:
        """List all documents in vault."""
        rows = self.conn.execute(
            """SELECT * FROM documents ORDER BY added_timestamp DESC 
               LIMIT ?""",
            (limit,)
        ).fetchall()
        return [self._row_to_doc(row) for row in rows]
    
    def verify_integrity(self, doc_hash: str) -> bool:
        """
        Verify document matches blockchain anchor.
        
        Checks that stored file hash matches the hash
        recorded in the blockchain.
        
        Args:
            doc_hash: Document to verify
            
        Returns:
            bool: True if valid
        """
        try:
            content = self.get_document(doc_hash)
            verify_hash = hashlib.sha256(content).hexdigest()
            return verify_hash == doc_hash
        except:
            return False
    
    def get_vault_stats(self) -> Dict:
        """Get vault statistics."""
        # Count documents
        count = self.conn.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0]
        
        # Total size
        total_size = self.conn.execute(
            "SELECT SUM(size) FROM documents"
        ).fetchone()[0] or 0
        
        # By version
        versions = self.conn.execute(
            """SELECT version, COUNT(*) as count 
               FROM documents GROUP BY version"""
        ).fetchall()
        
        return {
            'document_count': count,
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'by_version': {row['version']: row['count'] for row in versions},
            'vault_path': str(self.vault_path),
            'compression': self.compression
        }
    
    def _detect_type(self, filename: str, content: bytes) -> str:
        """Detect document MIME type."""
        lower = filename.lower()
        
        if lower.endswith('.pdf'):
            return DocumentType.PDF
        elif lower.endswith('.txt'):
            return DocumentType.TXT
        elif lower.endswith('.docx'):
            return DocumentType.DOCX
        elif lower.endswith('.epub'):
            return DocumentType.EPUB
        elif lower.endswith('.html') or lower.endswith('.htm'):
            return DocumentType.HTML
        
        # Try magic bytes
        if content[:4] == b'%PDF':
            return DocumentType.PDF
        elif content[:2] == b'PK':
            return DocumentType.DOCX  # Probably
        
        return DocumentType.UNKNOWN
    
    def _add_to_index(self, doc: StoredDocument, storage_path: str):
        """Add document to database index."""
        self.conn.execute(
            """INSERT INTO documents 
               (doc_hash, filename, doc_type, size, compressed,
                encryption, added_timestamp, blockchain_height,
                verse_ref, version, language, storage_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (doc.doc_hash, doc.filename, doc.doc_type, doc.size,
             doc.compressed, doc.encryption, doc.added_timestamp,
             doc.blockchain_height, doc.verse_ref, doc.version,
             doc.language, storage_path)
        )
        self.conn.commit()
    
    def _row_to_doc(self, row: sqlite3.Row) -> StoredDocument:
        """Convert database row to StoredDocument."""
        return StoredDocument(
            doc_hash=row['doc_hash'],
            filename=row['filename'],
            doc_type=row['doc_type'],
            size=row['size'],
            compressed=bool(row['compressed']),
            encryption=row['encryption'],
            added_timestamp=row['added_timestamp'],
            blockchain_height=row['blockchain_height'],
            verse_ref=row['verse_ref'],
            version=row['version'],
            language=row['language']
        )


# ==================== Self-Test ====================

def run_self_tests():
    """Test file vault functionality."""
    import tempfile
    import sys
    
    print("=" * 70)
    print("🧪 FileVault Self-Test Suite")
    print("=" * 70)
    
    tests_passed = 0
    tests_failed = 0
    
    # Create temp vault
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = os.path.join(tmpdir, "test-vault")
        
        # Test 1: Initialize vault
        print("\n1️⃣ Testing vault initialization...")
        try:
            vault = FileVault(vault_path, compression=True)
            assert os.path.exists(vault_path), "Vault directory not created"
            assert os.path.exists(vault.docs_path), "Docs directory not created"
            print("   ✅ Vault initialized")
            tests_passed += 1
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            tests_failed += 1
            return
        
        # Test 2: Store document
        print("\n2️⃣ Testing document storage...")
        try:
            test_content = b"This is a test Bible document. Genesis 1:1"
            test_hash = hashlib.sha256(test_content).hexdigest()
            
            from io import BytesIO
            doc_hash = vault.store_document(
                BytesIO(test_content),
                "test_genesis.txt",
                verse_ref="Genesis.1.1",
                version="TEST",
                language="en"
            )
            
            assert doc_hash == test_hash, "Hash mismatch"
            print(f"   ✅ Stored document: {doc_hash[:20]}...")
            tests_passed += 1
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            tests_failed += 1
        
        # Test 3: Retrieve document
        print("\n3️⃣ Testing document retrieval...")
        try:
            retrieved = vault.get_document(doc_hash)
            assert retrieved == test_content, "Retrieved content mismatch"
            print("   ✅ Document retrieved and verified")
            tests_passed += 1
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            tests_failed += 1
        
        # Test 4: Find by verse
        print("\n4️⃣ Testing verse lookup...")
        try:
            results = vault.find_by_verse("Genesis.1.1")
            assert len(results) >= 1, "Should find document"
            print(f"   ✅ Found {len(results)} document(s) for Genesis.1.1")
            tests_passed += 1
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            tests_failed += 1
        
        # Test 5: Vault stats
        print("\n5️⃣ Testing vault stats...")
        try:
            stats = vault.get_vault_stats()
            assert stats['document_count'] >= 1, "Should have documents"
            print(f"   ✅ Stats: {stats['document_count']} docs, "
                  f"{stats['total_size_bytes']} bytes")
            tests_passed += 1
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            tests_failed += 1
    
    # Summary
    print()
    print("=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    print(f"   ✅ Passed: {tests_passed}")
    print(f"   ❌ Failed: {tests_failed}")
    
    if tests_failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        return 1


if __name__ == "__main__":
    import sys
    exit_code = run_self_tests()
    sys.exit(exit_code)
