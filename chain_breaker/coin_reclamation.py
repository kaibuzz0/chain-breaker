# SECURITY FIX: Safe arithmetic operations
MAX_INT = 2**63 - 1

def safe_add(a, b):
    """Add with overflow check"""
    if a > MAX_INT - b:
        raise OverflowError("Integer overflow")
    return a + b

def safe_mul(a, b):
    """Multiply with overflow check"""
    if a > MAX_INT // b:
        raise OverflowError("Integer overflow")
    return a * b

def safe_sub(a, b):
    """Subtract with underflow check"""
    if a < b:
        raise ValueError("Insufficient balance")
    return a - b

"""
coin_reclamation.py

Reclaim dormant coins after years of inactivity.
Solves the 'lost Bitcoin forever' problem.

Mechanism:
- Track last activity per address
- After dormancy threshold (e.g., 10 years), coins enter 'reclaimable' state
- Owner can still recover with penalty (e.g., burn 10%)
- After longer period (e.g., 20 years), coins recycled to network
- Reclaimed coins fund development/security/miner rewards

This prevents permanent supply reduction from lost keys.
"""

import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class CoinState(Enum):
    """States a coin can be in."""
    ACTIVE = "active"
    DORMANT = "dormant"      # Warning period
    RECLAIMABLE = "reclaimable"  # Can recover with penalty
    RECYCLED = "recycled"    # Returned to network


@dataclass
class AddressStatus:
    """Track address activity and dormancy."""
    address: str
    balance: int
    last_activity: float  # Unix timestamp
    first_seen: float     # When address received funds
    
    # Configurable thresholds (in seconds)
    DORMANT_THRESHOLD: int = 10 * 365 * 24 * 3600   # 10 years
    RECLAIMABLE_THRESHOLD: int = 15 * 365 * 24 * 3600  # 15 years
    RECYCLE_THRESHOLD: int = 20 * 365 * 24 * 3600     # 20 years
    
    def get_state(self, current_time: Optional[float] = None) -> CoinState:
        """Determine coin state based on inactivity."""
        now = current_time or time.time()
        inactive = now - self.last_activity
        
        if inactive >= self.RECYCLE_THRESHOLD:
            return CoinState.RECYCLED
        elif inactive >= self.RECLAIMABLE_THRESHOLD:
            return CoinState.RECLAIMABLE
        elif inactive >= self.DORMANT_THRESHOLD:
            return CoinState.DORMANT
        else:
            return CoinState.ACTIVE
    
    def get_time_until_reclaimable(self, current_time: Optional[float] = None) -> float:
        """Get time until coins become reclaimable."""
        now = current_time or time.time()
        elapsed = now - self.last_activity
        remaining = self.RECLAIMABLE_THRESHOLD - elapsed
        return max(0, remaining)
    
    def get_time_until_recycled(self, current_time: Optional[float] = None) -> float:
        """Get time until coins recycled."""
        now = current_time or time.time()
        elapsed = now - self.last_activity
        remaining = self.RECYCLE_THRESHOLD - elapsed
        return max(0, remaining)


class CoinReclamation:
    """
    Manages dormant coin reclamation and recycling.
    
    Solves lost coin problem:
    - Bitcoin has ~20% supply lost forever (unrecoverable keys)
    - This is deflationary but wasteful
    - Reclamation allows recovery or redistribution
    """
    
    def __init__(
        self,
        dormant_threshold_years: float = 10.0,
        reclaimable_threshold_years: float = 15.0,
        recycle_threshold_years: float = 20.0,
        reclaim_penalty: float = 0.10,  # 10% burn to reclaim
        recycle_destination: str = "network_treasury"
    ):
        # Convert years to seconds
        self.dormant_threshold = dormant_threshold_years * 365 * 24 * 3600
        self.reclaimable_threshold = reclaimable_threshold_years * 365 * 24 * 3600
        self.recycle_threshold = recycle_threshold_years * 365 * 24 * 3600
        
        self.reclaim_penalty = reclaim_penalty
        self.recycle_destination = recycle_destination
        
        # Track addresses
        self.addresses: Dict[str, AddressStatus] = {}
        
        # Reclaimed funds
        self.reclaimed_pool: int = 0  # From penalties
        self.recycled_pool: int = 0   # From full recycling
        
        # Stats
        self.total_reclaimed: int = 0
        self.total_recycled: int = 0
        self.addresses_recycled: int = 0
    
    def register_address(self, address: str, balance: int, first_seen: float):
        """Register address for tracking."""
        if address not in self.addresses:
            self.addresses[address] = AddressStatus(
                address=address,
                balance=balance,
                last_activity=first_seen,
                first_seen=first_seen
            )
    
    def update_activity(self, address: str, timestamp: Optional[float] = None):
        """Update last activity for address."""
        if address in self.addresses:
            self.addresses[address].last_activity = timestamp or time.time()
    
    def get_address_state(self, address: str) -> Optional[CoinState]:
        """Get current state of address coins."""
        if address not in self.addresses:
            return None
        return self.addresses[address].get_state()
    
    def can_reclaim(self, address: str) -> Tuple[bool, str]:
        """
        Check if address can reclaim dormant coins.
        
        Returns:
            (can_reclaim, reason)
        """
        if address not in self.addresses:
            return False, "Address not tracked"
        
        status = self.addresses[address]
        state = status.get_state()
        
        if state == CoinState.ACTIVE:
            return False, "Coins are active"
        elif state == CoinState.DORMANT:
            return False, f"Coins dormant, reclaimable in {status.get_time_until_reclaimable()/86400:.0f} days"
        elif state == CoinState.RECLAIMABLE:
            return True, f"Reclaimable with {self.reclaim_penalty*100}% penalty"
        elif state == CoinState.RECYCLED:
            return False, "Coins already recycled"
        
        return False, "Unknown state"
    
    def reclaim_coins(self, address: str, proof_of_ownership: str) -> Dict[str, Any]:
        """
        Reclaim dormant coins.
        
        Owner pays penalty (burned) to recover remaining.
        This incentivizes keeping keys safe but allows recovery.
        """
        can_reclaim, reason = self.can_reclaim(address)
        
        if not can_reclaim:
            return {'success': False, 'reason': reason}
        
        status = self.addresses[address]
        total_balance = status.balance
        
        # Calculate penalty
        penalty = int(total_balance * self.reclaim_penalty)
        recovered = total_balance - penalty
        
        # Update state
        self.reclaimed_pool += penalty
        self.total_reclaimed += penalty
        
        # Reset activity (coins are now active again)
        self.update_activity(address)
        status.balance = recovered  # Remaining after penalty
        
        return {
            'success': True,
            'address': address,
            'original_balance': total_balance,
            'penalty': penalty,
            'recovered': recovered,
            'penalty_rate': self.reclaim_penalty,
        }
    
    def process_recycling(self, current_time: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Process automatic recycling of long-dormant coins.
        
        Called periodically (e.g., once per day).
        Returns list of recycled addresses.
        """
        now = current_time or time.time()
        recycled = []
        
        for address, status in list(self.addresses.items()):
            if status.get_state(now) == CoinState.RECYCLED:
                # Recycle coins
                amount = status.balance
                self.recycled_pool += amount
                self.total_recycled += amount
                self.addresses_recycled += 1
                
                # Clear balance
                status.balance = 0
                
                recycled.append({
                    'address': address,
                    'amount': amount,
                    'dormant_for_years': (now - status.last_activity) / (365 * 24 * 3600),
                    'recycled_at': now,
                })
        
        return recycled
    
    def distribute_recycled_funds(
        self,
        miners_share: float = 0.50,
        dev_share: float = 0.30,
        burn_share: float = 0.20
    ) -> Dict[str, int]:
        """
        Distribute recycled funds.
        
        Default:
        - 50% to miners (security budget)
        - 30% to development
        - 20% burned (deflationary)
        """
        if self.recycled_pool == 0:
            return {}
        
        total = self.recycled_pool
        
        distribution = {
            'miners': int(total * miners_share),
            'development': int(total * dev_share),
            'burned': int(total * burn_share),
        }
        
        # Clear pool
        self.recycled_pool = 0
        
        return distribution
    
    def get_dormant_stats(self) -> Dict[str, Any]:
        """Get statistics on dormant coins."""
        now = time.time()
        
        active = 0
        dormant = 0
        reclaimable = 0
        recycled = 0
        
        dormant_value = 0
        reclaimable_value = 0
        
        for status in self.addresses.values():
            state = status.get_state(now)
            
            if state == CoinState.ACTIVE:
                active += 1
            elif state == CoinState.DORMANT:
                dormant += 1
                dormant_safe_add(value, = status.balance
            elif state == CoinState.RECLAIMABLE:
                reclaimable += 1
                reclaimable_safe_add(value, = status.balance
            elif state == CoinState.RECYCLED:
                recycled += 1
        
        return {
            'total_addresses': len(self.addresses),
            'active': active,
            'dormant': dormant,
            'reclaimable': reclaimable,
            'recycled': recycled,
            'dormant_value': dormant_value,
            'reclaimable_value': reclaimable_value,
            'reclaimed_pool': self.reclaimed_pool,
            'recycled_pool': self.recycled_pool,
            'total_reclaimed': self.total_reclaimed,
            'total_recycled': self.total_recycled,
        }
    
    def simulate_years_passed(self, years: float):
        """Simulate time passing for testing."""
        seconds = years * 365 * 24 * 3600
        future_time = time.time() + seconds
        
        # Update all addresses as if time passed
        for status in self.addresses.values():
            # Don't actually update - just use future_time in queries
            pass
        
        return future_time


if __name__ == "__main__":
    print("=" * 60)
    print("COIN RECLAMATION - Dormant Coin Recovery")
    print("=" * 60)
    
    # Create reclamation system
    reclamation = CoinReclamation(
        dormant_threshold_years=10.0,
        reclaimable_threshold_years=15.0,
        recycle_threshold_years=20.0,
        reclaim_penalty=0.10,  # 10%
    )
    
    # Simulate addresses
    now = time.time()
    
    print("\nRegistering addresses...")
    
    # Active address
    reclamation.register_address("active_user", 10000, now)
    reclamation.update_activity("active_user", now)
    print("  active_user: 10,000 coins (active)")
    
    # 12-year dormant (reclaimable soon)
    twelve_years_ago = now - (12 * 365 * 24 * 3600)
    reclamation.register_address("dormant_12yr", 50000, twelve_years_ago)
    print("  dormant_12yr: 50,000 coins (12 years dormant)")
    
    # 18-year dormant (reclaimable now)
    eighteen_years_ago = now - (18 * 365 * 24 * 3600)
    reclamation.register_address("dormant_18yr", 100000, eighteen_years_ago)
    print("  dormant_18yr: 100,000 coins (18 years dormant)")
    
    # Check states
    print("\nAddress States:")
    for addr in ["active_user", "dormant_12yr", "dormant_18yr"]:
        state = reclamation.get_address_state(addr)
        can_reclaim, reason = reclamation.can_reclaim(addr)
        status = reclamation.addresses[addr]
        print(f"  {addr}: {state.value}, balance: {status.balance}")
        print(f"    Can reclaim: {can_reclaim} ({reason})")
    
    # Reclaim dormant 18yr
    print("\n" + "=" * 60)
    print("Reclaiming dormant_18yr coins...")
    result = reclamation.reclaim_coins("dormant_18yr", "proof_here")
    print(f"  Original: {result['original_balance']:,}")
    print(f"  Penalty (10%): {result['penalty']:,}")
    print(f"  Recovered: {result['recovered']:,}")
    print(f"  Success: {result['success']}")
    
    # Stats
    print("\n" + "=" * 60)
    print("Reclamation Statistics:")
    stats = reclamation.get_dormant_stats()
    print(f"  Total addresses: {stats['total_addresses']}")
    print(f"  Active: {stats['active']}")
    print(f"  Dormant: {stats['dormant']} ({stats['dormant_value']:,} coins)")
    print(f"  Reclaimable: {stats['reclaimable']} ({stats['reclaimable_value']:,} coins)")
    print(f"  Reclaimed pool: {stats['reclaimed_pool']:,}")
    print(f"  Total reclaimed: {stats['total_reclaimed']:,}")
    
    print("\n" + "=" * 60)
    print("Coin reclamation: Lost coins can be recovered or recycled")
    print("=" * 60)
