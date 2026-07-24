"""
Scripture Validator
===================

Validates scripture references and anchors.
"""

from typing import Optional, Tuple, List
import hashlib
import re
from .reference import ScriptureReference, ScriptureAnchor, Version


class ScriptureValidator:
    """Validates Biblical scripture references."""
    
    CANONICAL_BOOKS = {
        "Genesis": 50, "Exodus": 40, "Leviticus": 27, "Numbers": 36, "Deuteronomy": 34,
        "Joshua": 24, "Judges": 21, "Ruth": 4, "1 Samuel": 31, "2 Samuel": 24,
        "1 Kings": 22, "2 Kings": 25, "1 Chronicles": 29, "2 Chronicles": 36,
        "Ezra": 10, "Nehemiah": 13, "Esther": 10, "Job": 42, "Psalms": 150,
        "Proverbs": 31, "Ecclesiastes": 12, "Song of Solomon": 8, "Isaiah": 66,
        "Jeremiah": 52, "Lamentations": 5, "Ezekiel": 48, "Daniel": 12, "Hosea": 14,
        "Joel": 3, "Amos": 9, "Obadiah": 1, "Jonah": 4, "Micah": 7,
        "Nahum": 3, "Habakkuk": 3, "Zephaniah": 3, "Haggai": 2, "Zechariah": 14,
        "Malachi": 4, "Matthew": 28, "Mark": 16, "Luke": 24, "John": 21,
        "Acts": 28, "Romans": 16, "1 Corinthians": 16, "2 Corinthians": 13,
        "Galatians": 6, "Ephesians": 6, "Philippians": 4, "Colossians": 4,
        "1 Thessalonians": 5, "2 Thessalonians": 3, "1 Timothy": 6, "2 Timothy": 4,
        "Titus": 3, "Philemon": 1, "Hebrews": 13, "James": 5, "1 Peter": 5,
        "2 Peter": 3, "1 John": 5, "2 John": 1, "3 John": 1, "Jude": 1,
        "Revelation": 22
    }
    
    MAX_VERSES_PER_CHAPTER = 176
    
    def __init__(self):
        self.validated_count = 0
        self.rejected_count = 0
    
    def validate_reference(self, ref: ScriptureReference) -> Tuple[bool, Optional[str]]:
        """Validate a scripture reference."""
        if ref.book not in self.CANONICAL_BOOKS:
            return False, f"Book '{ref.book}' not in canonical list"
        
        max_chapters = self.CANONICAL_BOOKS[ref.book]
        
        if ref.chapter < 1 or ref.chapter > max_chapters:
            return False, f"Chapter {ref.chapter} out of range"
        
        if ref.verse_start < 1:
            return False, "Verse must be >= 1"
        
        if ref.verse_start > self.MAX_VERSES_PER_CHAPTER:
            return False, f"Verse exceeds maximum"
        
        if ref.verse_end < ref.verse_start:
            return False, "End verse must be >= start verse"
        
        self.validated_count += 1
        return True, None
    
    def validate_anchor(self, anchor: ScriptureAnchor) -> Tuple[bool, Optional[str]]:
        """Validate a complete scripture anchor."""
        is_valid, error = self.validate_reference(anchor.reference)
        if not is_valid:
            self.rejected_count += 1
            return False, error
        
        if not re.match(r'^[a-f0-9]{64}$', anchor.text_hash):
            self.rejected_count += 1
            return False, "Invalid text hash format"
        
        import time
        if anchor.timestamp > time.time() + 86400:
            self.rejected_count += 1
            return False, "Timestamp too far in future"
        
        self.validated_count += 1
        return True, None
    
    def get_stats(self) -> dict:
        """Get validation statistics."""
        return {
            "validated": self.validated_count,
            "rejected": self.rejected_count,
            "total": self.validated_count + self.rejected_count
        }


class TextHasher:
    """Standardized text hashing for scripture."""
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text for consistent hashing."""
        text = re.sub(r'^\d+\s*', '', text)
        text = ' '.join(text.split())
        text = text.lower()
        import unicodedata
        text = unicodedata.normalize('NFKD', text)
        return text
    
    @classmethod
    def hash_text(cls, text: str) -> str:
        """Compute standardized hash."""
        normalized = cls.normalize_text(text)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
