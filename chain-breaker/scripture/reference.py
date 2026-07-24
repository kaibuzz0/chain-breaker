"""
Scripture Reference and Anchoring
==================================

Data structures for Biblical text anchoring on the blockchain.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List
from enum import Enum
import hashlib
import json


class Version(Enum):
    """Supported Bible versions."""
    HEBREW_MASORETIC = "WLC"      # Westminster Leningrad Codex
    GREEK_SEPTUAGINT = "LXX"      # Septuagint
    GREEK_TEXTUS_RECEPTUS = "TR"  # Textus Receptus
    LATIN_VULGATE = "VUL"         # Latin Vulgate
    ENGLISH_KJV = "KJV"           # King James Version
    ENGLISH_ESV = "ESV"           # English Standard Version
    ENGLISH_NIV = "NIV"           # New International Version


@dataclass
class ScriptureReference:
    """
    Reference to a specific Bible passage.
    
    Supports multiple formats:
    - Genesis 1:1
    - John 3:16-17 (range)
    - Psalm 23:1-6 (full chapter)
    """
    book: str
    chapter: int
    verse_start: int
    verse_end: Optional[int] = None
    version: Version = Version.ENGLISH_KJV
    
    def __post_init__(self):
        if self.verse_end is None:
            self.verse_end = self.verse_start
    
    def to_string(self) -> str:
        """Convert to human-readable string."""
        if self.verse_start == self.verse_end:
            return f"{self.book} {self.chapter}:{self.verse_start}"
        else:
            return f"{self.book} {self.chapter}:{self.verse_start}-{self.verse_end}"
    
    def to_canonical_id(self) -> str:
        """Generate canonical ID for blockchain storage."""
        book_normalized = self.book.lower().replace(" ", "_")
        return f"{book_normalized}:{self.chapter}:{self.verse_start}:{self.verse_end}:{self.version.value}"
    
    @classmethod
    def from_string(cls, ref_str: str, version: Version = Version.ENGLISH_KJV) -> "ScriptureReference":
        """
        Parse reference from string.
        
        Examples:
            Genesis 1:1
            John 3:16-17
            Psalm 23
        """
        # Basic parsing - supports "Book Ch:V" and "Book Ch:V-V" formats
        parts = ref_str.strip().rsplit(" ", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid reference format: {ref_str}")
        
        book = parts[0]
        verse_part = parts[1]
        
        chapter_str, verse_str = verse_part.split(":")
        chapter = int(chapter_str)
        
        if "-" in verse_str:
            start, end = verse_str.split("-")
            verse_start = int(start)
            verse_end = int(end)
        else:
            verse_start = int(verse_str)
            verse_end = verse_start
        
        return cls(
            book=book,
            chapter=chapter,
            verse_start=verse_start,
            verse_end=verse_end,
            version=version
        )


@dataclass
class ScriptureAnchor:
    """
    Blockchain transaction for anchoring scripture.
    
    This is the core data structure for preserving Biblical text
    on the blockchain with cryptographic proof.
    """
    reference: ScriptureReference
    text_hash: str           # SHA-256 hash of the text content
    text_preview: str        # First 100 chars (for display)
    timestamp: float
    authority_signature: Optional[str] = None
    e8_commitment: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """Serialize for blockchain storage."""
        return {
            "type": "scripture_anchor",
            "reference": self.reference.to_canonical_id(),
            "text_hash": self.text_hash,
            "text_preview": self.text_preview,
            "timestamp": self.timestamp,
            "authority_signature": self.authority_signature,
            "e8_commitment": self.e8_commitment
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ScriptureAnchor":
        """Deserialize from blockchain storage."""
        ref_parts = data["reference"].split(":")
        reference = ScriptureReference(
            book=ref_parts[0].replace("_", " ").title(),
            chapter=int(ref_parts[1]),
            verse_start=int(ref_parts[2]),
            verse_end=int(ref_parts[3]),
            version=Version(ref_parts[4])
        )
        
        return cls(
            reference=reference,
            text_hash=data["text_hash"],
            text_preview=data["text_preview"],
            timestamp=data["timestamp"],
            authority_signature=data.get("authority_signature"),
            e8_commitment=data.get("e8_commitment")
        )
    
    def compute_hash(self) -> str:
        """Compute hash for blockchain inclusion."""
        data = self.to_dict()
        # Exclude signature from hash computation
        data.pop("authority_signature", None)
        data.pop("e8_commitment", None)
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()


class ScriptureDatabase:
    """
    SQLite-backed database for scripture anchors.
    
    Mobile-optimized for Termux/Android deployment.
    """
    
    def __init__(self, db_path: str = "scripture.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scripture_anchors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_id TEXT UNIQUE NOT NULL,
                book TEXT NOT NULL,
                chapter INTEGER NOT NULL,
                verse_start INTEGER NOT NULL,
                verse_end INTEGER NOT NULL,
                version TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                text_preview TEXT,
                timestamp REAL NOT NULL,
                block_hash TEXT,
                authority_signature TEXT,
                e8_commitment TEXT
            )
        """)
        
        # Index for quick lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_scripture_lookup 
            ON scripture_anchors(book, chapter)
        """)
        
        conn.commit()
        conn.close()
    
    def store_anchor(self, anchor: ScriptureAnchor, block_hash: Optional[str] = None):
        """Store a scripture anchor in the database."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        e8_json = json.dumps(anchor.e8_commitment) if anchor.e8_commitment else None
        
        cursor.execute("""
            INSERT OR REPLACE INTO scripture_anchors 
            (canonical_id, book, chapter, verse_start, verse_end, version,
             text_hash, text_preview, timestamp, block_hash, authority_signature, e8_commitment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            anchor.reference.to_canonical_id(),
            anchor.reference.book,
            anchor.reference.chapter,
            anchor.reference.verse_start,
            anchor.reference.verse_end,
            anchor.reference.version.value,
            anchor.text_hash,
            anchor.text_preview,
            anchor.timestamp,
            block_hash,
            anchor.authority_signature,
            e8_json
        ))
        
        conn.commit()
        conn.close()
    
    def get_anchor(self, ref: ScriptureReference) -> Optional[ScriptureAnchor]:
        """Retrieve a scripture anchor by reference."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM scripture_anchors WHERE canonical_id = ?
        """, (ref.to_canonical_id(),))
        
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        # Reconstruct from database
        return ScriptureAnchor(
            reference=ref,
            text_hash=row[7],
            text_preview=row[8],
            timestamp=row[9],
            authority_signature=row[11],
            e8_commitment=json.loads(row[12]) if row[12] else None
        )
    
    def get_anchors_by_book(self, book: str) -> List[ScriptureAnchor]:
        """Get all anchors for a specific book."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM scripture_anchors WHERE book = ? ORDER BY chapter, verse_start
        """, (book,))
        
        anchors = []
        for row in cursor.fetchall():
            ref = ScriptureReference(
                book=row[2],
                chapter=row[3],
                verse_start=row[4],
                verse_end=row[5],
                version=Version(row[6])
            )
            anchors.append(ScriptureAnchor(
                reference=ref,
                text_hash=row[7],
                text_preview=row[8],
                timestamp=row[9],
                authority_signature=row[11],
                e8_commitment=json.loads(row[12]) if row[12] else None
            ))
        
        conn.close()
        return anchors
    
    def get_stats(self) -> Dict:
        """Get database statistics."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM scripture_anchors")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT book) FROM scripture_anchors")
        books = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT version) FROM scripture_anchors")
        versions = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_anchors": total,
            "books_covered": books,
            "versions": versions
        }
