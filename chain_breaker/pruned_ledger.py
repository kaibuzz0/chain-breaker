"""
pruned_ledger.py

Storage-efficient ledger with pruning.
- Keeps last N blocks in full
- Archives older blocks (headers + commitments only)
- Verifies chain integrity without full history
- Target: 100x storage reduction vs full chain

For Pi nodes: Keep ~1000 recent blocks (~100MB)
Archive rest as headers only (~10KB per 1000 blocks)
"""

import time
import json
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from .chain_ledger import Ledger
from .block_core import Block, BlockHeader
from .hash_engine import HashEngine, MerkleTree
from .binary_codec import BinaryCodec


@dataclass
class PrunedBlock:
    """
    Minimal block representation for archived blocks.
    Only what we need for verification, not full transactions.
    """
    hash: str
    header: Dict[str, Any]
    tx_count: int
    tx_merkle_root: str
    # Note: Actual transactions not stored here
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'hash': self.hash,
            'header': self.header,
            'tx_count': self.tx_count,
            'tx_merkle_root': self.tx_merkle_root,
        }
    
    @classmethod
    def from_block(cls, block: Block) -> 'PrunedBlock':
        """Create pruned version from full block."""
        # Compute tx merkle root
        tx_hashes = [HashEngine.hash_object(tx) for tx in block.transactions]
        tree = MerkleTree(tx_hashes)
        
        return cls(
            hash=block.hash,
            header=block.header.to_dict(),
            tx_count=len(block.transactions),
            tx_merkle_root=HashEngine.hash_to_hex(tree.root) if tree.root else "0" * 64,
        )


class PrunedLedger:
    """
    Ledger with automatic pruning for resource-constrained nodes.
    
    Strategy:
    - Recent blocks: Full data (transactions, everything)
    - Old blocks: Headers only (enough for verification)
    - Ancient blocks: Just hash chain (proof of existence)
    
    This lets a Pi node participate fully without storing GBs.
    """
    
    def __init__(
        self,
        keep_full_blocks: int = 1000,  # Keep last 1000 blocks full
        archive_after: int = 10000,     # Archive after 10k blocks
        prune_after: int = 100000,     # Prune to just headers after 100k
    ):
        self.keep_full_blocks = keep_full_blocks
        self.archive_after = archive_after
        self.prune_after = prune_after
        
        # Full blocks (recent)
        self.full_chain: List[Block] = []
        
        # Archived blocks (headers + merkle roots)
        self.archived: Dict[int, PrunedBlock] = {}
        
        # Pruned blocks (just hash for verification)
        self.pruned_hashes: Dict[int, str] = {}
        
        # State (balances, etc - reconstructed from recent blocks)
        self.state: Dict[str, int] = {}
        self.state_height = 0
        
        # UTXO set (for quick balance lookups)
        self.utxo_set: Dict[str, Dict[str, Any]] = {}
        
        # Create genesis
        self._create_genesis()
    
    def _create_genesis(self):
        """Create and store genesis block."""
        from .block_core import create_genesis_block
        genesis = create_genesis_block()
        self.full_chain.append(genesis)
        self._update_state_from_block(genesis)
    
    @property
    def height(self) -> int:
        """Current chain height."""
        return len(self.full_chain) + len(self.archived) + len(self.pruned_hashes) - 1
    
    @property
    def last_block(self) -> Block:
        """Most recent full block."""
        return self.full_chain[-1]
    
    def get_block(self, index: int) -> Optional[Block]:
        """
        Get block by index.
        Returns full block if available, None if archived/pruned.
        """
        # In full chain
        if index < len(self.full_chain):
            return self.full_chain[index]
        return None
    
    def get_block_header(self, index: int) -> Optional[Dict[str, Any]]:
        """Get block header by index (works for all blocks)."""
        # Full chain
        if index < len(self.full_chain):
            return self.full_chain[index].header.to_dict()
        
        # Archived
        archived_idx = index - len(self.full_chain)
        if archived_idx in self.archived:
            return self.archived[archived_idx].header
        
        return None
    
    def add_transaction(self, transaction: Dict[str, Any]) -> bool:
        """Add transaction to next block (same as base ledger)."""
        # Just store in pending - will be added next mine
        if not hasattr(self, '_pending'):
            self._pending = []
        self._pending.append(transaction)
        return True
    
    def mine_pending(self, miner_address: str) -> Optional[Block]:
        """
        Mine pending transactions and add to chain.
        With automatic pruning if thresholds reached.
        """
        # Get pending or empty
        pending = getattr(self, '_pending', [])
        
        # Build block on top of last
        from .block_core import Block, BlockHeader
        from .chain_ledger import Ledger
        
        # Create coinbase
        coinbase = {
            'type': 'coinbase',
            'to': miner_address,
            'amount': 100,  # Mining reward
            'height': self.height + 1,
        }
        
        transactions = [coinbase] + pending
        
        # Build Merkle tree
        tx_hashes = [HashEngine.hash_object(tx) for tx in transactions]
        tree = MerkleTree(tx_hashes)
        
        header = BlockHeader(
            version=1,
            prev_hash=self.last_block.hash,
            merkle_root=HashEngine.hash_to_hex(tree.root) if tree.root else "0" * 64,
            difficulty=2,
        )
        
        block = Block(header=header, transactions=transactions)
        block.mine()
        
        if block.verify():
            self._add_block(block)
            self._pending = []  # Clear pending
            return block
        
        return None
    
    def _add_block(self, block: Block):
        """Add block with automatic pruning."""
        current_height = self.height
        
        # Add to full chain
        self.full_chain.append(block)
        self._update_state_from_block(block)
        
        # Prune if needed
        self._prune_if_needed()
    
    def _update_state_from_block(self, block: Block):
        """Update UTXO state from block transactions."""
        for tx in block.transactions:
            # Update balances (simplified)
            if 'to' in tx:
                addr = tx['to']
                if addr not in self.state:
                    self.state[addr] = 0
                self.state[addr] += tx.get('amount', 0)
            
            if 'from' in tx and tx.get('from') != 'genesis':
                addr = tx['from']
                if addr not in self.state:
                    self.state[addr] = 0
                self.state[addr] -= tx.get('amount', 0)
        
        self.state_height = self.height
    
    def _prune_if_needed(self):
        """Prune old blocks if thresholds exceeded."""
        if len(self.full_chain) > self.keep_full_blocks:
            # Move oldest full blocks to archive
            to_archive = self.full_chain[:-self.keep_full_blocks]
            self.full_chain = self.full_chain[-self.keep_full_blocks:]
            
            for block in to_archive:
                idx = self.state_height - len(self.full_chain) - len(to_archive) + to_archive.index(block)
                self.archived[idx] = PrunedBlock.from_block(block)
        
        if len(self.archived) > self.archive_after:
            # Move oldest archived to pruned (just hash)
            sorted_indices = sorted(self.archived.keys())
            to_prune = sorted_indices[:-self.archive_after]
            
            for idx in to_prune:
                self.pruned_hashes[idx] = self.archived[idx].hash
                del self.archived[idx]
    
    def get_balance(self, address: str) -> int:
        """Get balance from state (fast)."""
        return self.state.get(address, 0)
    
    def validate_chain(self) -> bool:
        """Validate chain integrity using available data."""
        # Validate full chain
        for i in range(1, len(self.full_chain)):
            current = self.full_chain[i]
            previous = self.full_chain[i - 1]
            
            if not current.verify():
                return False
            
            if current.header.prev_hash != previous.hash:
                return False
        
        # Check archived headers link correctly
        # (Just verify hash chain continuity)
        last_full_hash = self.full_chain[0].header.prev_hash if len(self.full_chain) > 0 else ""
        
        for idx in sorted(self.archived.keys()):
            archived = self.archived[idx]
            if archived.header['prev_hash'] != last_full_hash:
                return False
            last_full_hash = archived.hash
        
        return True
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Report storage usage."""
        # Estimate sizes (rough)
        full_size = len(self.full_chain) * 1024  # ~1KB per block
        archive_size = len(self.archived) * 200    # ~200 bytes per archived
        pruned_size = len(self.pruned_hashes) * 64  # Just hash
        
        total_size = full_size + archive_size + pruned_size
        height = self.height
        
        # Avoid division by zero
        if height <= 0 or total_size == 0:
            savings = "0%"
        else:
            full_chain_size = height * 1024
            savings_pct = ((full_chain_size - total_size) / full_chain_size * 100)
            savings = f"{savings_pct:.1f}%"
        
        return {
            'height': height,
            'full_blocks': len(self.full_chain),
            'archived_blocks': len(self.archived),
            'pruned_blocks': len(self.pruned_hashes),
            'estimated_full_mb': full_size / (1024 * 1024),
            'estimated_archive_mb': archive_size / (1024 * 1024),
            'estimated_pruned_mb': pruned_size / (1024 * 1024),
            'total_estimated_mb': total_size / (1024 * 1024),
            'savings_vs_full': savings,
        }


if __name__ == "__main__":
    print("PrunedLedger Test")
    print("=" * 50)
    
    # Create ledger with small thresholds for demo
    ledger = PrunedLedger(
        keep_full_blocks=5,     # Keep only 5 full
        archive_after=10,       # Archive after 10
        prune_after=20,         # Prune after 20
    )
    
    print(f"Initial height: {ledger.height}")
    
    # Mine many blocks to trigger pruning
    for i in range(15):
        ledger.add_transaction({
            'from': 'alice',
            'to': 'bob',
            'amount': 10 + i
        })
        ledger.mine_pending(f"miner{i}")
    
    print(f"\nAfter mining 15 blocks:")
    stats = ledger.get_storage_stats()
    print(f"  Height: {stats['height']}")
    print(f"  Full blocks: {stats['full_blocks']}")
    print(f"  Archived: {stats['archived_blocks']}")
    print(f"  Pruned: {stats['pruned_blocks']}")
    print(f"  Est. storage: {stats['total_estimated_mb']:.4f} MB")
    print(f"  Chain valid: {ledger.validate_chain()}")
    
    print(f"\nBalances:")
    print(f"  Alice: {ledger.get_balance('alice')}")
    print(f"  Bob: {ledger.get_balance('bob')}")
    
    print("\n" + "=" * 50)
    print("Pruned ledger working - storage optimized!")
