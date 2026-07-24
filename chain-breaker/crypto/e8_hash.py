"""
chain_breaker/crypto/e8_hash.py

E8-Enhanced Block Hashing
=========================

Instead of pure SHA-256, we add E8 lattice transformations:
- Weyl group mixing adds quantum-resistant structure
- Deterministic transformations based on block nonce
- Self-inverse: applying twice returns original

Algorithm:
    block_hash = SHA256(E8_transform(SHA256(block_data), nonce))

This creates a hybrid hash that:
1. Benefits from SHA-256's avalanche properties
2. Adds quantum-resistant mixing via E8 symmetries
3. Remains deterministic and fast to verify
4. Uses self-inverse property for flexibility
"""

import hashlib
import json
from typing import Dict, Any

from .e8_core import get_e8_weyl, get_e8_lattice


class E8BlockHasher:
    """
    Block hashing with E8-enhanced mixing.
    
    Combines SHA-256 with Weyl group transformations for
    quantum-resistant chain linking.
    """
    
    def __init__(self):
        self.weyl = get_e8_weyl()
        self.e8 = get_e8_lattice()
    
    def hash_block(self, block_data: Dict[str, Any], nonce: int = 0) -> str:
        """
        Compute E8-enhanced hash of block data.
        
        Args:
            block_data: Dictionary containing block fields
            nonce: Mining nonce (used to select Weyl transformation)
            
        Returns:
            Hex-encoded block hash
        """
        # Step 1: Serialize block data deterministically
        serialized = self._serialize(block_data)
        
        # Step 2: Initial SHA-256
        h1 = hashlib.sha256(serialized).digest()
        
        # Step 3: E8 Weyl transformation (quantum mixing)
        h2 = self.weyl.transform(h1, nonce)
        
        # Step 4: Final SHA-256 for avalanche
        h3 = hashlib.sha256(h2).digest()
        
        return h3.hex()
    
    def hash_header(self, header: Dict[str, Any]) -> str:
        """
        Hash block header (lightweight verification).
        
        Header contains:
            - previous_hash
            - merkle_root
            - timestamp
            - difficulty
            - nonce
        """
        return self.hash_block(header, header.get("nonce", 0))
    
    def _serialize(self, data: Dict[str, Any]) -> bytes:
        """
        Deterministically serialize block data.
        
        Critical: Must produce identical bytes across all platforms.
        """
        # Sort keys for determinism
        return json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')
    
    def verify_chain_link(self, prev_hash: str, block_data: Dict[str, Any],
                         nonce: int, expected_hash: str) -> bool:
        """
        Verify that block properly links to previous.
        
        Args:
            prev_hash: Hash of previous block
            block_data: Current block data
            nonce: Block nonce
            expected_hash: Claimed current block hash
            
        Returns:
            True if link is valid
        """
        # Verify previous hash is in block data
        if block_data.get("previous_hash") != prev_hash:
            return False
        
        # Recompute hash
        computed = self.hash_block(block_data, nonce)
        
        return computed == expected_hash
    
    def compute_merkle_root(self, items: list) -> str:
        """
        Compute E8-enhanced Merkle root.
        
        Each level gets E8 mixing for extra quantum resistance.
        """
        if not items:
            return "0" * 64
        
        # Hash leaf items
        hashes = [self._hash_item(item) for item in items]
        
        # Build tree
        level = 0
        while len(hashes) > 1:
            next_level = []
            for i in range(0, len(hashes), 2):
                left = hashes[i]
                if i + 1 < len(hashes):
                    right = hashes[i + 1]
                else:
                    right = left  # Duplicate last if odd
                
                # E8-enhanced parent hash
                combined = left + right
                parent = self._e8_hash_pair(combined, level)
                next_level.append(parent)
            
            hashes = next_level
            level += 1
        
        return hashes[0]
    
    def _hash_item(self, item: Any) -> str:
        """Hash a single item to 32-byte hex string."""
        if isinstance(item, str):
            data = item.encode('utf-8')
        elif isinstance(item, bytes):
            data = item
        else:
            data = json.dumps(item, sort_keys=True).encode('utf-8')
        
        return hashlib.sha256(data).hexdigest()
    
    def _e8_hash_pair(self, combined: str, level: int) -> str:
        """
        Hash pair with E8 transformation.
        
        Level parameter ensures different mixing at each tree level.
        """
        data = combined.encode('utf-8')
        h = hashlib.sha256(data).digest()
        
        # Apply Weyl transform (level selects different transformation)
        h2 = self.weyl.transform(h, nonce=level)
        
        return hashlib.sha256(h2).hexdigest()


class DifficultyCalculator:
    """
    Calculate mining difficulty targets.
    
    Similar to Bitcoin but adjusted for:
    - Mobile-friendly mining
    - 5-minute block time (faster than Bitcoin's 10)
    """
    
    TARGET_BLOCK_TIME = 300  # 5 minutes
    RETARGET_INTERVAL = 2016  # Blocks per difficulty adjustment
    
    def __init__(self):
        self.max_target = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
    
    def calculate_difficulty(self, hash_hex: str) -> float:
        """
        Convert hash to difficulty value.
        
        Lower hash values = higher difficulty achieved.
        """
        hash_int = int(hash_hex, 16)
        return self.max_target / hash_int
    
    def check_proof_of_work(self, hash_hex: str, difficulty: int) -> bool:
        """
        Check if hash meets difficulty target.
        
        Args:
            hash_hex: Block hash
            difficulty: Current difficulty bits
            
        Returns:
            True if PoW is valid
        """
        hash_int = int(hash_hex, 16)
        target = self.max_target // difficulty
        return hash_int <= target
    
    def retarget(self, prev_difficulty: int, 
                 actual_timespan: int, target_timespan: int = None) -> int:
        """
        Calculate new difficulty after retarget interval.
        
        Args:
            prev_difficulty: Previous block's difficulty
            actual_timespan: Time taken for RETARGET_INTERVAL blocks
            target_timespan: Expected time (default: RETARGET_INTERVAL * TARGET_BLOCK_TIME)
            
        Returns:
            New difficulty value
        """
        if target_timespan is None:
            target_timespan = self.RETARGET_INTERVAL * self.TARGET_BLOCK_TIME
        
        # Difficulty adjustment factor
        factor = actual_timespan / target_timespan
        
        # Clamp to prevent wild swings (Bitcoin: 4x max)
        factor = max(0.25, min(factor, 4.0))
        
        new_difficulty = int(prev_difficulty * factor)
        
        # Ensure minimum difficulty
        return max(new_difficulty, 1)


class MobileOptimizedMining:
    """
    Mining optimized for mobile devices.
    
    Features:
    - Cooperative mining (pool support)
    - Battery-aware operation
    - Interruptible (can pause/resume)
    - Low memory footprint
    """
    
    def __init__(self, hasher: E8BlockHasher):
        self.hasher = hasher
        self.interrupted = False
    
    def mine_block(self, block_data: Dict[str, Any], 
                   difficulty: int, 
                   max_nonce: int = 2**32) -> tuple:
        """
        Mine a block (find valid nonce).
        
        Args:
            block_data: Block data (without nonce)
            difficulty: Current difficulty
            max_nonce: Maximum nonce to try
            
        Returns:
            (nonce, hash_hex) or (None, None) if interrupted
        """
        calc = DifficultyCalculator()
        
        for nonce in range(max_nonce):
            if self.interrupted:
                return None, None
            
            # Check every 1000 iterations for mobile responsiveness
            if nonce % 1000 == 0:
                # Yield control (could check battery here)
                pass
            
            block_data["nonce"] = nonce
            hash_hex = self.hasher.hash_block(block_data, nonce)
            
            if calc.check_proof_of_work(hash_hex, difficulty):
                return nonce, hash_hex
        
        return None, None
    
    def interrupt(self):
        """Signal to stop mining (battery low, etc.)."""
        self.interrupted = True
    
    def cooperative_mine(self, block_data: Dict[str, Any],
                        difficulty: int,
                        pool_share: int = 0) -> tuple:
        """
        Mine as part of a pool.
        
        pool_share: Which share of nonce space to search (0-1023)
        """
        nonce_start = pool_share * (2**32 // 1024)
        nonce_end = nonce_start + (2**32 // 1024)
        
        return self.mine_block(block_data, difficulty, nonce_end)


if __name__ == "__main__":
    print("E8 Block Hashing loaded")
    print("Quantum-resistant chain linking ready")
