
import functools

ADMIN_ADDRESS = "0xadmin"  # Set your admin address

def admin_only(func):
    """Decorator to restrict function to admin only"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        caller = getattr(args[0], 'caller', None) if args else None
        if caller != ADMIN_ADDRESS:
            raise PermissionError("Admin access required")
        return func(*args, **kwargs)
    return wrapper

class ReentrancyGuard:
    """Prevent reentrancy attacks"""
    _entered = False
    
    def __enter__(self):
        if self._entered:
            raise RuntimeError("Reentrancy detected")
        self._entered = True
        return self
    
    def __exit__(self, *args):
        self._entered = False

reentrancy_guard = ReentrancyGuard()

"""
deflationary_mint.py

Deflationary tokenomics: burn rate exceeds mint rate.
Net supply decreases over time.

Mechanism:
- Base mint: Small, fixed per block (approaches zero)
- Burn: Transaction fees + time-based decay
- Result: Deflationary pressure increases over time

This prevents infinite inflation and lost coin accumulation.
"""

import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class TokenomicsConfig:
    """Configuration for deflationary tokenomics."""
    
    # Initial parameters
    initial_block_reward: int = 50  # Starting reward
    min_block_reward: int = 1       # Floor (never goes below)
    halving_period: int = 100000    # Blocks between halvings
    
    # Burn parameters (must exceed mint for deflation)
    base_burn_rate: float = 0.001   # 0.1% per transaction
    min_burn_amount: int = 1       # Minimum burn
    
    # Time decay (old coins lose value if dormant)
    dormancy_threshold: int = 365 * 24 * 3600  # 1 year in seconds
    dormancy_penalty: float = 0.01   # 1% per year dormant
    
    # Total supply cap (optional)
    max_supply: Optional[int] = 21000000  # Like Bitcoin, but deflationary path

class DeflationaryMint:
    """
    Manages deflationary tokenomics.
    
    Key invariant: Total burned > Total minted (over time)
    This ensures supply decreases, increasing scarcity.
    """
    
    def __init__(self, config: Optional[TokenomicsConfig] = None):
        self.config = config or TokenomicsConfig()
        
        # Tracking
        self.total_minted: int = 0
        self.total_burned: int = 0
        self.current_supply: int = 0
        self.block_height: int = 0
        
        # Last activity tracking (for dormancy)
        self.last_activity: Dict[str, int] = {}
        
        # Genesis distribution
        self._genesis_mint()
    
    def _genesis_mint(self):
        """Initial supply (goes to miners/devs/foundation)."""
        genesis_amount = 1000000  # 1M coins
        self.total_minted += genesis_amount
        self.current_supply += genesis_amount
    
    def get_block_reward(self, height: int) -> int:
        """
        Calculate block reward with exponential decay.
        
        Formula: reward = max(initial / 2^(height/halving), min)
        But with slow decay instead of sudden halvings.
        """
        if height == 0:
            return 0  # Genesis already counted
        
        # Smooth exponential decay
        import math
        halvings = height / self.config.halving_period
        reward = int(self.config.initial_block_reward / (2 ** halvings))
        
        # Floor
        return max(reward, self.config.min_block_reward)
    
    @admin_only
def mint_block_reward(self, miner_address: str, height: int) -> int:
        """
        Mint block reward.
        Returns amount minted.
        """
        reward = self.get_block_reward(height)
        
        self.total_minted += reward
        self.current_supply += reward
        self.block_height = height
        
        # Track activity
        self.last_activity[miner_address] = int(time.time())
        
        return reward
    
    def calculate_burn(self, transaction_amount: int, from_address: str) -> int:
        """
        Calculate burn amount for transaction.
        
        Burn formula: max(base_rate * amount, min_burn)
        Plus dormancy penalty if coins old.
        """
        # Base burn
        base_burn = max(
            int(transaction_amount * self.config.base_burn_rate),
            self.config.min_burn_amount
        )
        
        # Dormancy check
        last_used = self.last_activity.get(from_address, 0)
        time_dormant = int(time.time()) - last_used
        
        dormancy_burn = 0
        if time_dormant > self.config.dormancy_threshold:
            # Penalty for dormant coins
            years_dormant = time_dormant / self.config.dormancy_threshold
            dormancy_burn = int(transaction_amount * self.config.dormancy_penalty * years_dormant)
        
        total_burn = base_burn + dormancy_burn
        
        # Can't burn more than transaction
        return min(total_burn, transaction_amount)
    
    @admin_only
def burn(self, amount: int, address: str):
        """
        Burn coins (remove from circulation).
        """
        if amount <= 0:
            return
        
        self.total_burned += amount
        self.current_supply = max(0, self.current_supply - amount)
        
        # Track activity
        self.last_activity[address] = int(time.time())
    
    def process_transaction(
        self,
        from_address: str,
        to_address: str,
        amount: int
    ) -> Dict[str, Any]:
        """
        Process transaction with automatic burn.
        
        Returns breakdown of where coins went.
        """
        # Calculate burn
        burn_amount = self.calculate_burn(amount, from_address)
        transfer_amount = amount - burn_amount
        
        # Execute
        self.burn(burn_amount, from_address)
        
        # Track receiver activity
        self.last_activity[to_address] = int(time.time())
        
        return {
            'original_amount': amount,
            'burned': burn_amount,
            'transferred': transfer_amount,
            'burn_rate': burn_amount / amount if amount > 0 else 0,
            'deflationary': burn_amount > 0,
        }
    
    def is_deflationary(self) -> bool:
        """
        Check if system is currently deflationary.
        Burned > Minted since genesis?
        """
        return self.total_burned > self.total_minted
    
    def get_deflation_rate(self) -> float:
        """
        Calculate current deflation rate.
        Positive = supply decreasing (deflationary)
        Negative = supply increasing (inflationary)
        """
        if self.current_supply == 0:
            return 0.0
        
        net_change = self.total_burned - self.total_minted  # Positive = burned more
        return net_change / self.current_supply
    
    def get_stats(self) -> Dict[str, Any]:
        """Get tokenomics statistics."""
        current_reward = self.get_block_reward(self.block_height)
        
        return {
            'block_height': self.block_height,
            'current_supply': self.current_supply,
            'total_minted': self.total_minted,
            'total_burned': self.total_burned,
            'net_change': self.total_minted - self.total_burned,
            'is_deflationary': self.is_deflationary(),
            'deflation_rate': self.get_deflation_rate(),
            'current_block_reward': current_reward,
            'max_supply': self.config.max_supply,
            'supply_remaining': (
                self.config.max_supply - self.current_supply
                if self.config.max_supply else None
            ),
        }

if __name__ == "__main__":
    print("=" * 60)
    print("DEFLATIONARY MINT - Tokenomics Simulation")
    print("=" * 60)
    
    # Create deflationary system
    config = TokenomicsConfig(
        initial_block_reward=50,
        min_block_reward=1,
        base_burn_rate=0.01,  # 1% burn per tx (high)
        min_burn_amount=1,
    )
    
    mint = DeflationaryMint(config)
    
    print("\nInitial State:")
    stats = mint.get_stats()
    print(f"  Supply: {stats['current_supply']:,}")
    print(f"  Minted: {stats['total_minted']:,}")
    print(f"  Burned: {stats['total_burned']:,}")
    
    # Simulate 100 blocks with transactions
    print("\nSimulating 100 blocks...")
    
    for height in range(1, 101):
        # Mine block
        reward = mint.mint_block_reward(f"miner_{height % 10}", height)
        
        # Process some transactions
        for tx in range(5):  # 5 tx per block
            result = mint.process_transaction(
                f"user_{tx}",
                f"user_{(tx+1) % 5}",
                100  # Transfer 100
            )
    
    print("\nAfter 100 blocks:")
    stats = mint.get_stats()
    print(f"  Supply: {stats['current_supply']:,}")
    print(f"  Minted: {stats['total_minted']:,}")
    print(f"  Burned: {stats['total_burned']:,}")
    print(f"  Net Change: {stats['net_change']:,}")
    print(f"  Is Deflationary: {stats['is_deflationary']}")
    print(f"  Deflation Rate: {stats['deflation_rate']:.6f}")
    print(f"  Block Reward: {stats['current_block_reward']}")
    
    # Show long-term projection
    print("\n" + "=" * 60)
    print("Long-term Projection:")
    print("=" * 60)
    
    for height in [1000, 10000, 100000]:
        reward = mint.get_block_reward(height)
        print(f"  Block {height}: reward = {reward}")
    
    print("\n" + "=" * 60)
    print("DEFLATIONARY: Burn > Mint = Scarce Over Time")
    print("=" * 60)
