"""
hash_engine.py

Cryptographic primitives for blockchain.
- SHA256 hashing
- Double-SHA256 (Bitcoin standard)
- Merkle tree construction
- Hash pointers
"""

import hashlib
import json
from typing import List, Any, Optional
from dataclasses import dataclass


class HashEngine:
    """SHA256 operations optimized for blockchain use."""
    
    @staticmethod
    def sha256(data: bytes) -> bytes:
        """Single SHA256 hash."""
        return hashlib.sha256(data).digest()
    
    @staticmethod
    def double_sha256(data: bytes) -> bytes:
        """Double SHA256 (Bitcoin standard)."""
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()
    
    @staticmethod
    def hash_to_hex(data: bytes) -> str:
        """Convert hash bytes to hex string."""
        return data.hex()
    
    @classmethod
    def hash_object(cls, obj: Any) -> bytes:
        """Hash any JSON-serializable object."""
        data = json.dumps(obj, sort_keys=True).encode('utf-8')
        return cls.sha256(data)


class MerkleTree:
    """
    Binary Merkle tree for transaction verification.
    Efficient inclusion proofs with O(log n) verification.
    """
    
    def __init__(self, leaves: List[bytes]):
        self.leaves = leaves
        self.levels = self._build_tree()
    
    def _build_tree(self) -> List[List[bytes]]:
        """Build tree bottom-up."""
        if not self.leaves:
            return []
        
        levels = [self.leaves]
        current = self.leaves
        
        while len(current) > 1:
            next_level = []
            for i in range(0, len(current), 2):
                left = current[i]
                right = current[i + 1] if i + 1 < len(current) else left
                parent = HashEngine.double_sha256(left + right)
                next_level.append(parent)
            current = next_level
            levels.append(current)
        
        return levels
    
    @property
    def root(self) -> Optional[bytes]:
        """Merkle root hash."""
        if not self.levels:
            return None
        return self.levels[-1][0]
    
    def get_proof(self, index: int) -> List[bytes]:
        """Get inclusion proof for leaf at index."""
        proof = []
        for level in self.levels[:-1]:
            sibling_idx = index + 1 if index % 2 == 0 else index - 1
            if sibling_idx < len(level):
                proof.append(level[sibling_idx])
            index //= 2
        return proof
    
    @staticmethod
    def verify_proof(root: bytes, leaf: bytes, proof: List[bytes], index: int) -> bool:
        """Verify inclusion proof."""
        current = leaf
        for sibling in proof:
            if index % 2 == 0:
                current = HashEngine.double_sha256(current + sibling)
            else:
                current = HashEngine.double_sha256(sibling + current)
            index //= 2
        return current == root


if __name__ == "__main__":
    print("HashEngine Test")
    he = HashEngine()
    
    # Test basic hash
    data = b"Hello Chain"
    h1 = he.sha256(data)
    print(f"  SHA256: {he.hash_to_hex(h1)[:16]}...")
    
    h2 = he.double_sha256(data)
    print(f"  Double-SHA256: {he.hash_to_hex(h2)[:16]}...")
    
    print("\nMerkleTree Test")
    leaves = [he.sha256(f"tx{i}".encode()) for i in range(4)]
    tree = MerkleTree(leaves)
    print(f"  Root: {he.hash_to_hex(tree.root)[:16]}...")
    
    # Test proof
    proof = tree.get_proof(1)
    print(f"  Proof for leaf 1: {len(proof)} nodes")
    
    verified = MerkleTree.verify_proof(tree.root, leaves[1], proof, 1)
    print(f"  Verification: {verified}")
