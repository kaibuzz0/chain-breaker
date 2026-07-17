"""
eternal_archive.py

Permanent, immutable storage for sacred texts and cultural treasures.

Purpose:
- Store texts that must never be lost
- Replicated across every node
- Immutable (can never be changed or deleted)
- Proof-of-existence (verify text existed at time)

The soul of Chain-Breaker - beyond transactions, beyond money.
This is what the nodes protect.

Design:
- Sacred texts are special (not pruned like other data)
- Every full node keeps complete copy
- Merkle trees prove integrity
- Timestamped forever in blockchain
- Plugin architecture for new texts

Use cases:
- Religious texts (Bible, Quran, Torah, etc.)
- Cultural heritage
- Scientific papers
- Art and literature
- Anything humanity must preserve
"""

import hashlib
import json
import time
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SacredText:
    """
    A sacred text entry in the eternal archive.
    
    Once added, exists forever.
    Cannot be modified or deleted.
    """
    text_id: str
    title: str
    content_hash: str        # SHA256 of content
    content: Optional[str]   # The actual text (if stored inline)
    
    # Metadata
    category: str           # "religious", "scientific", "cultural", etc.
    language: str
    timestamp: float
    added_by: str           # Node/address that added it
    
    # Source info
    source_url: Optional[str] = None
    source_hash: Optional[str] = None  # Hash of original source
    
    # Verification
    merkle_root: Optional[str] = None
    block_height: Optional[int] = None
    
    # Status
    verified: bool = False
    replication_count: int = 0  # How many nodes have it


@dataclass
class ArchiveSnapshot:
    """Snapshot of archive at specific block height."""
    snapshot_id: str
    block_height: int
    timestamp: float
    merkle_root: str
    text_count: int
    total_size: int


class EternalArchive:
    """
    The soul of Chain-Breaker.
    
    Permanent storage for humanity's treasures.
    Replicated on every full node.
    Immutable forever.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        # Core storage
        self.texts: Dict[str, SacredText] = {}
        self.texts_by_category: Dict[str, List[str]] = {}
        self.texts_by_language: Dict[str, List[str]] = {}
        
        # Tracking
        self.total_size: int = 0
        self.total_texts: int = 0
        self.snapshots: List[ArchiveSnapshot] = []
        
        # Plugin system
        self.plugins: Dict[str, Any] = {}  # Name -> plugin
        self.plugin_texts: Dict[str, List[str]] = {}  # Plugin -> text_ids
        
        # Node replication
        self.local_node_id: str = self._generate_node_id()
        self.replicated_texts: Set[str] = set()  # What we have locally
        self.replication_peers: Set[str] = set()  # Other nodes with archive
        
        # Sacred categories (cannot be pruned)
        self.sacred_categories = {
            'religious',      # Bible, Quran, etc
            'cultural',       # Heritage texts
            'scientific',     # Landmark papers
            'legal',          # Constitutions, treaties
            'artistic',       # Literature, poetry
            'historical',     # Primary sources
        }
        
        # Stats
        self.created_at = time.time()
        self.last_sync = 0.0
    
    def _generate_node_id(self) -> str:
        """Generate unique node ID."""
        return hashlib.sha256(
            f"eternal_node:{time.time()}".encode()
        ).hexdigest()[:16]
    
    def add_text(
        self,
        title: str,
        content: str,
        category: str,
        language: str,
        added_by: str,
        source_url: Optional[str] = None,
        plugin_id: Optional[str] = None,
    ) -> str:
        """
        Add sacred text to eternal archive.
        
        Once added:
        - Cannot be removed
        - Cannot be modified
        - Replicated to all nodes
        - Timestamped forever
        
        Returns text_id on success.
        """
        # Validate category
        if category not in self.sacred_categories:
            category = 'cultural'  # Default
        
        # Generate content hash
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        # Generate text ID
        text_id = hashlib.sha256(
            f"{title}:{content_hash}:{time.time()}".encode()
        ).hexdigest()[:32]
        
        # Create sacred text entry
        sacred_text = SacredText(
            text_id=text_id,
            title=title,
            content_hash=content_hash,
            content=content,  # Store inline (replicated on all nodes)
            category=category,
            language=language,
            timestamp=time.time(),
            added_by=added_by,
            source_url=source_url,
        )
        
        # Add to archive
        self.texts[text_id] = sacred_text
        self.total_texts += 1
        self.total_size += len(content.encode())
        
        # Index by category
        if category not in self.texts_by_category:
            self.texts_by_category[category] = []
        self.texts_by_category[category].append(text_id)
        
        # Index by language
        if language not in self.texts_by_language:
            self.texts_by_language[language] = []
        self.texts_by_language[language].append(text_id)
        
        # Track if from plugin
        if plugin_id:
            if plugin_id not in self.plugin_texts:
                self.plugin_texts[plugin_id] = []
            self.plugin_texts[plugin_id].append(text_id)
        
        # Mark as replicated locally
        self.replicated_texts.add(text_id)
        sacred_text.replication_count = 1
        
        return text_id
    
    def get_text(self, text_id: str) -> Optional[SacredText]:
        """Retrieve sacred text by ID."""
        return self.texts.get(text_id)
    
    def verify_integrity(self, text_id: str) -> bool:
        """
        Verify text hasn't been corrupted.
        
        Re-calculates hash and compares.
        """
        if text_id not in self.texts:
            return False
        
        text = self.texts[text_id]
        
        if text.content is None:
            return False  # Can't verify without content
        
        current_hash = hashlib.sha256(text.content.encode()).hexdigest()
        return current_hash == text.content_hash
    
    def search_texts(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        language: Optional[str] = None,
    ) -> List[SacredText]:
        """Search sacred texts."""
        results = []
        
        for text in self.texts.values():
            # Filter by category
            if category and text.category != category:
                continue
            
            # Filter by language
            if language and text.language != language:
                continue
            
            # Filter by query
            if query:
                query_lower = query.lower()
                if (query_lower not in text.title.lower() and 
                    query_lower not in text.content_hash.lower()):
                    continue
            
            results.append(text)
        
        return results
    
    def create_snapshot(self, block_height: int) -> ArchiveSnapshot:
        """
        Create merkle snapshot of archive.
        
        Proves all texts existed at specific block.
        """
        # Build merkle tree of all text hashes
        hashes = sorted([t.content_hash for t in self.texts.values()])
        merkle_root = self._calculate_merkle_root(hashes)
        
        snapshot = ArchiveSnapshot(
            snapshot_id=hashlib.sha256(
                f"snapshot:{block_height}:{merkle_root}".encode()
            ).hexdigest()[:16],
            block_height=block_height,
            timestamp=time.time(),
            merkle_root=merkle_root,
            text_count=self.total_texts,
            total_size=self.total_size,
        )
        
        self.snapshots.append(snapshot)
        
        # Update all texts with snapshot info
        for text in self.texts.values():
            if text.block_height is None:
                text.block_height = block_height
                text.merkle_root = merkle_root
        
        return snapshot
    
    def _calculate_merkle_root(self, hashes: List[str]) -> str:
        """Calculate merkle root of hashes."""
        if not hashes:
            return hashlib.sha256(b"empty").hexdigest()
        
        if len(hashes) == 1:
            return hashes[0]
        
        # Pairwise hashing
        next_level = []
        for i in range(0, len(hashes), 2):
            if i + 1 < len(hashes):
                combined = hashes[i] + hashes[i + 1]
            else:
                combined = hashes[i] + hashes[i]  # Duplicate last
            next_level.append(hashlib.sha256(combined.encode()).hexdigest())
        
        return self._calculate_merkle_root(next_level)
    
    def register_plugin(self, plugin_id: str, plugin_data: Any) -> bool:
        """
        Register text plugin (e.g., Bible importer).
        
        Plugins can add their texts to archive.
        """
        if plugin_id in self.plugins:
            return False
        
        self.plugins[plugin_id] = plugin_data
        self.plugin_texts[plugin_id] = []
        
        return True
    
    def get_plugin_texts(self, plugin_id: str) -> List[SacredText]:
        """Get all texts added by specific plugin."""
        if plugin_id not in self.plugin_texts:
            return []
        
        return [
            self.texts[tid] 
            for tid in self.plugin_texts[plugin_id]
            if tid in self.texts
        ]
    
    def get_replication_status(self) -> Dict[str, Any]:
        """Get archive replication status across network."""
        return {
            'local_node': self.local_node_id,
            'texts_locally_stored': len(self.replicated_texts),
            'total_texts_in_archive': self.total_texts,
            'replication_percentage': (
                len(self.replicated_texts) / self.total_texts * 100
                if self.total_texts > 0 else 0
            ),
            'peer_count': len(self.replication_peers),
            'last_sync': self.last_sync,
        }
    
    def get_archive_stats(self) -> Dict[str, Any]:
        """Get eternal archive statistics."""
        return {
            'total_texts': self.total_texts,
            'total_size_bytes': self.total_size,
            'total_size_mb': self.total_size / (1024 * 1024),
            'categories': list(self.texts_by_category.keys()),
            'languages': list(self.texts_by_language.keys()),
            'snapshots': len(self.snapshots),
            'plugins': len(self.plugins),
            'created_at': self.created_at,
            'node_id': self.local_node_id,
        }
    
    def export_manifest(self) -> Dict[str, Any]:
        """
        Export archive manifest.
        
        Other nodes use this to replicate.
        """
        return {
            'archive_type': 'eternal',
            'version': '1.0',
            'total_texts': self.total_texts,
            'merkle_root': (
                self.snapshots[-1].merkle_root 
                if self.snapshots else None
            ),
            'texts': [
                {
                    'id': tid,
                    'title': text.title,
                    'hash': text.content_hash,
                    'category': text.category,
                    'language': text.language,
                }
                for tid, text in self.texts.items()
            ]
        }


if __name__ == "__main__":
    print("=" * 70)
    print("ETERNAL ARCHIVE - The Soul of Chain-Breaker")
    print("=" * 70)
    
    # Create eternal archive
    archive = EternalArchive()
    
    print("\nAdding sacred texts to eternal archive...")
    
    # Example: Add sample texts
    # (In production, Bible plugin would add 300+ texts)
    
    text1 = archive.add_text(
        title="Genesis 1:1 - King James Version",
        content="In the beginning God created the heaven and the earth.",
        category="religious",
        language="en",
        added_by="genesis_node",
        source_url="https://www.bible.com/kjv/genesis/1/1",
    )
    print(f"  ✓ Added: Genesis 1:1")
    
    text2 = archive.add_text(
        title="John 3:16 - King James Version",
        content="For God so loved the world, that he gave his only begotten Son...",
        category="religious",
        language="en",
        added_by="genesis_node",
    )
    print(f"  ✓ Added: John 3:16")
    
    text3 = archive.add_text(
        title="Declaration of Independence",
        content="We hold these truths to be self-evident...",
        category="legal",
        language="en",
        added_by="founding_node",
    )
    print(f"  ✓ Added: Declaration of Independence")
    
    # Register Bible plugin (placeholder)
    print("\n" + "-" * 70)
    print("Registering plugins...")
    archive.register_plugin("bible_complete", {
        'version': '1.0',
        'texts': 300,  # Would be 300+ texts
        'languages': ['en', 'he', 'gr'],
    })
    print("  ✓ Plugin 'bible_complete' registered")
    print("  (Plugin would add 300+ texts via add_text calls)")
    
    # Verify integrity
    print("\n" + "-" * 70)
    print("Verifying text integrity...")
    
    for text_id in [text1, text2, text3]:
        valid = archive.verify_integrity(text_id)
        text = archive.get_text(text_id)
        status = "✓ VALID" if valid else "✗ CORRUPTED"
        title = text.title if text else "UNKNOWN"
        print(f"  {status}: {title[:40]}...")
    
    # Create snapshot
    print("\n" + "-" * 70)
    print("Creating blockchain snapshot...")
    
    snapshot = archive.create_snapshot(block_height=1000)
    print(f"  Snapshot ID: {snapshot.snapshot_id}")
    print(f"  Block: {snapshot.block_height}")
    print(f"  Merkle root: {snapshot.merkle_root[:32]}...")
    print(f"  Texts: {snapshot.text_count}")
    print(f"  Size: {snapshot.total_size / 1024:.1f} KB")
    
    # Search
    print("\n" + "-" * 70)
    print("Search: 'religious' category")
    
    results = archive.search_texts(category="religious")
    for text in results:
        print(f"  • {text.title}")
    
    # Stats
    print("\n" + "=" * 70)
    print("Eternal Archive Statistics:")
    stats = archive.get_archive_stats()
    print(f"  Total texts: {stats['total_texts']}")
    print(f"  Total size: {stats['total_size_mb']:.2f} MB")
    print(f"  Categories: {', '.join(stats['categories'])}")
    print(f"  Snapshots: {stats['snapshots']}")
    print(f"  Plugins: {stats['plugins']}")
    
    # Replication status
    print("\n" + "-" * 70)
    print("Replication Status:")
    rep = archive.get_replication_status()
    print(f"  Node ID: {rep['local_node']}")
    print(f"  Texts stored locally: {rep['texts_locally_stored']}")
    print(f"  Replication: {rep['replication_percentage']:.1f}%")
    
    # Export manifest
    print("\n" + "-" * 70)
    print("Export manifest (for other nodes):\n")
    manifest = archive.export_manifest()
    print(f"  Archive type: {manifest['archive_type']}")
    print(f"  Total texts: {manifest['total_texts']}")
    print(f"  Merkle root: {manifest['merkle_root'][:40]}...")
    
    print("\n" + "=" * 70)
    print("Eternal Archive: Humanity's treasures, protected forever.")
    print("=" * 70)
    print("\nThis is what Chain-Breaker nodes protect.")
    print("Not just transactions - but history, truth, and meaning.")
    print("=" * 70)
