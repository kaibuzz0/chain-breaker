"""
Proof of Work Consensus Module
==============================

Battery-aware mining with interrupt support for mobile devices.
"""

import time
import threading
from typing import Optional, Tuple

# Import E8 hasher
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from chain_breaker.crypto.e8_hash import E8BlockHasher, DifficultyCalculator


class PoWMiner:
    """
    Proof of Work miner optimized for mobile devices.
    
    Features:
    - Interruptible mining (can stop for battery conservation)
    - Batch nonce checking for efficiency
    - Configurable difficulty and timeout
    """
    
    def __init__(self, batch_size: int = 1000):
        self.batch_size = batch_size
        self.interrupt_event = threading.Event()
        self.hasher = E8BlockHasher()
        self.difficulty_calc = DifficultyCalculator()
    
    def mine_block(self, block_data: dict, difficulty: int, 
                  max_nonce: int = 2**32, timeout: Optional[float] = None) -> Tuple[Optional[int], Optional[str]]:
        """
        Mine a block to find valid nonce.
        
        Args:
            block_data: Block data dictionary (without hash)
            difficulty: Mining difficulty target
            max_nonce: Maximum nonce to try
            timeout: Optional timeout in seconds
            
        Returns:
            (nonce, hash) or (None, None) if interrupted
        """
        self.interrupt_event.clear()
        start_time = time.time()
        
        for nonce in range(max_nonce):
            # Check for interruption
            if self.interrupt_event.is_set():
                return None, None
            
            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                return None, None
            
            # Compute hash
            hash_hex = self.hasher.hash_block(block_data, nonce)
            
            # Check if meets difficulty
            if self.difficulty_calc.check_proof_of_work(hash_hex, difficulty):
                return nonce, hash_hex
            
            # Batch yield for mobile responsiveness
            if nonce % self.batch_size == 0:
                time.sleep(0.001)  # 1ms yield
        
        return None, None
    
    def verify_proof(self, block_data: dict, nonce: int, hash_hex: str, difficulty: int) -> bool:
        """Verify a mined proof."""
        # Recompute hash
        computed = self.hasher.hash_block(block_data, nonce)
        
        # Check hash matches
        if computed != hash_hex:
            return False
        
        # Check difficulty
        return self.difficulty_calc.check_proof_of_work(hash_hex, difficulty)
    
    def interrupt(self):
        """Signal miner to stop (e.g., battery low)."""
        self.interrupt_event.set()
    
    def cooperative_mine(self, block_data: dict, difficulty: int,
                        pool_share: int, total_shares: int = 1024) -> Tuple[Optional[int], Optional[str]]:
        """
        Mine a portion of nonce space (for pool mining).
        
        Args:
            pool_share: Which share to mine (0 to total_shares-1)
            total_shares: Total number of shares
            
        Returns:
            (nonce, hash) or (None, None)
        """
        nonce_range = 2**32 // total_shares
        start_nonce = pool_share * nonce_range
        end_nonce = start_nonce + nonce_range
        
        return self.mine_block(block_data, difficulty, max_nonce=end_nonce)


class MobileMiningManager:
    """
    Manager for mobile-optimized mining operations.
    
    Handles:
    - Battery level checking
    - Mining session management
    - Interrupt on low battery
    """
    
    def __init__(self):
        self.miner = PoWMiner()
        self.is_mining = False
        self.battery_threshold = 20  # Stop if battery below 20%
    
    def check_battery(self) -> float:
        """
        Check current battery level.
        
        Returns:
            Battery percentage (0-100) or 100 if unknown
        """
        try:
            # Try to read Android battery (Termux)
            with open("/sys/class/power_supply/battery/capacity") as f:
                return float(f.read().strip())
        except:
            # Unknown battery level - assume OK
            return 100.0
    
    def can_mine(self) -> bool:
        """Check if mining is allowed based on battery."""
        return self.check_battery() > self.battery_threshold
    
    def start_mining(self, block_data: dict, difficulty: int) -> Optional[Tuple[int, str]]:
        """
        Start mining if battery allows.
        
        Returns:
            (nonce, hash) or None if cannot mine
        """
        if not self.can_mine():
            return None
        
        self.is_mining = True
        try:
            result = self.miner.mine_block(block_data, difficulty)
            return result
        finally:
            self.is_mining = False
    
    def stop_mining(self):
        """Stop current mining operation."""
        self.miner.interrupt()
        self.is_mining = False
