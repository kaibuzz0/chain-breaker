"""
state_rent.py

Storage rent system for sustainable blockchain economics.

Problem: "Store once, pay forever" leads to infinite state growth.

Solution:
- Pay recurring rent for on-chain storage
- Storage evicted if rent unpaid
- Prevents spam and state bloat
- Makes storage a scarce resource

This ensures the blockchain stays small and sustainable.
"""

import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class StorageStatus(Enum):
    """Status of stored data."""
    ACTIVE = "active"           # Rent paid, data safe
    WARNING = "warning"         # Rent running low
    EXPIRED = "expired"         # Rent unpaid, eviction imminent
    EVICTED = "evicted"         # Data removed


@dataclass
class StorageSlot:
    """Single storage slot with rent tracking."""
    key: str                    # Storage key
    size_bytes: int             # Size of data
    rent_rate: int              # Rent per period (per byte)
    last_rent_payment: float    # Timestamp
    rent_balance: int           # Pre-paid rent
    
    def calculate_rent_due(self, current_time: Optional[float] = None) -> int:
        """Calculate rent owed since last payment."""
        now = current_time or time.time()
        time_elapsed = now - self.last_rent_payment
        
        # Rent = size * rate * time
        # Simplified: 1 period = 1 day (86400 seconds)
        periods = time_elapsed / 86400
        return int(self.size_bytes * self.rent_rate * periods)
    
    def get_time_until_eviction(self, current_time: Optional[float] = None) -> float:
        """Get seconds until storage evicted."""
        now = current_time or time.time()
        rent_due = self.calculate_rent_due(now)
        
        if rent_due >= self.rent_balance:
            return 0
        
        # How long will current balance last?
        daily_rent = self.size_bytes * self.rent_rate
        if daily_rent == 0:
            return float('inf')
        
        remaining = self.rent_balance - rent_due
        days_left = remaining / daily_rent
        return days_left * 86400
    
    def get_status(self, current_time: Optional[float] = None) -> StorageStatus:
        """Get current storage status."""
        now = current_time or time.time()
        rent_due = self.calculate_rent_due(now)
        
        if rent_due > self.rent_balance:
            return StorageStatus.EXPIRED
        elif rent_due > self.rent_balance * 0.8:  # 80% used
            return StorageStatus.WARNING
        else:
            return StorageStatus.ACTIVE


@dataclass
class AccountStorage:
    """All storage for an account."""
    address: str
    slots: Dict[str, StorageSlot] = field(default_factory=dict)
    total_size: int = 0
    created_at: float = field(default_factory=time.time)
    
    def add_slot(self, key: str, size: int, rent_rate: int, initial_deposit: int):
        """Add new storage slot."""
        slot = StorageSlot(
            key=key,
            size_bytes=size,
            rent_rate=rent_rate,
            last_rent_payment=time.time(),
            rent_balance=initial_deposit,
        )
        self.slots[key] = slot
        self.total_size += size
    
    def pay_rent(self, key: str, amount: int) -> bool:
        """Pay rent for specific slot."""
        if key not in self.slots:
            return False
        
        slot = self.slots[key]
        
        # Deduct rent due first
        rent_due = slot.calculate_rent_due()
        if rent_due > 0:
            slot.rent_balance -= rent_due
            slot.last_rent_payment = time.time()
        
        # Add new deposit
        slot.rent_balance += amount
        return True
    
    def get_total_rent_due(self) -> int:
        """Get total rent due across all slots."""
        return sum(slot.calculate_rent_due() for slot in self.slots.values())
    
    def evict_slot(self, key: str):
        """Evict storage slot for non-payment."""
        if key in self.slots:
            self.total_size -= self.slots[key].size_bytes
            del self.slots[key]


class StateRent:
    """
    State rent management system.
    
    Ensures sustainable storage by requiring ongoing payment.
    Prevents "store once, pay forever" problem.
    """
    
    def __init__(
        self,
        base_rent_rate: int = 1,          # Per byte per day
        min_deposit: int = 100,           # Minimum initial deposit
        eviction_grace_period: int = 7,  # Days after expiry before eviction
    ):
        self.base_rate = base_rent_rate
        self.min_deposit = min_deposit
        self.grace_period = eviction_grace_period * 86400  # Seconds
        
        # Storage tracking
        self.accounts: Dict[str, AccountStorage] = {}
        self.evicted_slots: List[Tuple[str, str, float]] = []  # addr, key, time
        
        # Stats
        self.total_storage_bytes = 0
        self.total_rent_collected = 0
        self.total_evicted = 0
    
    def store_data(
        self,
        address: str,
        key: str,
        data_size: int,
        initial_deposit: int,
    ) -> bool:
        """
        Store data on-chain with rent prepayment.
        
        Requires upfront deposit for initial rent period.
        """
        if initial_deposit < self.min_deposit:
            return False
        
        if data_size <= 0:
            return False
        
        # Get or create account
        if address not in self.accounts:
            self.accounts[address] = AccountStorage(address=address)
        
        account = self.accounts[address]
        
        # Calculate rent rate (could vary by data type)
        rent_rate = self.base_rate
        
        # Add storage slot
        account.add_slot(key, data_size, rent_rate, initial_deposit)
        self.total_storage_bytes += data_size
        
        return True
    
    def pay_rent(self, address: str, key: str, amount: int) -> bool:
        """Pay rent for specific storage slot."""
        if address not in self.accounts:
            return False
        
        return self.accounts[address].pay_rent(key, amount)
    
    def check_evictions(self) -> int:
        """
        Process expired storage evictions.
        
        Called periodically (e.g., once per day).
        """
        evicted = 0
        now = time.time()
        
        for address, account in list(self.accounts.items()):
            for key, slot in list(account.slots.items()):
                status = slot.get_status(now)
                
                if status == StorageStatus.EXPIRED:
                    # Check grace period
                    time_expired = now - (slot.last_rent_payment + 
                                       (slot.rent_balance / (slot.size_bytes * slot.rent_rate) * 86400))
                    
                    if time_expired > self.grace_period:
                        # Evict
                        account.evict_slot(key)
                        self.evicted_slots.append((address, key, now))
                        self.total_storage_bytes -= slot.size_bytes
                        self.total_evicted += 1
                        evicted += 1
            
            # Clean up empty accounts
            if not account.slots:
                del self.accounts[address]
        
        return evicted
    
    def get_storage_info(self, address: str, key: str) -> Optional[Dict[str, Any]]:
        """Get storage slot information."""
        if address not in self.accounts:
            return None
        
        account = self.accounts[address]
        if key not in account.slots:
            return None
        
        slot = account.slots[key]
        
        return {
            'address': address,
            'key': key,
            'size_bytes': slot.size_bytes,
            'rent_rate': slot.rent_rate,
            'rent_balance': slot.rent_balance,
            'rent_due': slot.calculate_rent_due(),
            'time_until_eviction': slot.get_time_until_eviction(),
            'status': slot.get_status().value,
        }
    
    def get_account_summary(self, address: str) -> Optional[Dict[str, Any]]:
        """Get summary of account storage."""
        if address not in self.accounts:
            return None
        
        account = self.accounts[address]
        
        total_slots = len(account.slots)
        warning_slots = sum(1 for s in account.slots.values() 
                          if s.get_status() == StorageStatus.WARNING)
        expired_slots = sum(1 for s in account.slots.values() 
                          if s.get_status() == StorageStatus.EXPIRED)
        
        return {
            'address': address,
            'total_slots': total_slots,
            'total_size': account.total_size,
            'total_rent_due': account.get_total_rent_due(),
            'warning_slots': warning_slots,
            'expired_slots': expired_slots,
        }
    
    def estimate_storage_cost(self, data_size: int, days: int) -> int:
        """
        Estimate cost to store data for N days.
        
        Helps users budget for storage.
        """
        daily_rent = data_size * self.base_rate
        return daily_rent * days
    
    def get_network_stats(self) -> Dict[str, Any]:
        """Get network-wide storage statistics."""
        total_accounts = len(self.accounts)
        total_slots = sum(len(a.slots) for a in self.accounts.values())
        
        # Calculate total rent being paid
        total_rent_per_day = sum(
            sum(s.size_bytes * s.rent_rate for s in a.slots.values())
            for a in self.accounts.values()
        )
        
        return {
            'total_accounts': total_accounts,
            'total_slots': total_slots,
            'total_storage_bytes': self.total_storage_bytes,
            'avg_storage_per_account': (
                self.total_storage_bytes / total_accounts if total_accounts > 0 else 0
            ),
            'total_rent_per_day': total_rent_per_day,
            'total_evicted_slots': self.total_evicted,
            'base_rate': self.base_rate,
        }
    
    def compare_storage_models(self) -> Dict[str, Dict]:
        """Compare rent model vs traditional permanent storage."""
        return {
            'traditional': {
                'payment': 'One-time',
                'cost': 'Fixed at store time',
                'eviction': 'Never',
                'state_growth': 'Infinite',
                'sustainability': 'Unsustainable',
            },
            'rent_model': {
                'payment': 'Recurring',
                'cost': 'Proportional to size and time',
                'eviction': 'If unpaid',
                'state_growth': 'Bounded by economics',
                'sustainability': 'Sustainable',
            },
        }


if __name__ == "__main__":
    print("=" * 60)
    print("STATE RENT - Sustainable Storage Economics")
    print("=" * 60)
    
    # Create rent system
    rent = StateRent(
        base_rent_rate=1,      # 1 unit per byte per day
        min_deposit=100,
        eviction_grace_period=7,
    )
    
    print("\nStoring data with rent prepayment...")
    
    # Alice stores contract data
    result1 = rent.store_data(
        address="alice",
        key="contract_storage",
        data_size=1000,      # 1KB
        initial_deposit=5000,  # Pre-pay for ~5 days
    )
    print(f"  Alice: 1KB contract data (deposit: 5000)")
    
    # Bob stores NFT metadata
    result2 = rent.store_data(
        address="bob",
        key="nft_metadata",
        data_size=500,       # 500 bytes
        initial_deposit=2000,
    )
    print(f"  Bob: 500B NFT metadata (deposit: 2000)")
    
    # Check storage info
    print("\n" + "-" * 60)
    print("Storage Information:")
    
    info1 = rent.get_storage_info("alice", "contract_storage")
    if info1:
        print(f"\n  Alice contract:")
        print(f"    Size: {info1['size_bytes']} bytes")
        print(f"    Rent rate: {info1['rent_rate']}/byte/day")
        print(f"    Balance: {info1['rent_balance']}")
        print(f"    Rent due: {info1['rent_due']}")
        print(f"    Status: {info1['status']}")
        print(f"    Time until eviction: {info1['time_until_eviction']:.0f}s")
    
    # Simulate time passing
    print("\n" + "-" * 60)
    print("Simulating 10 days passing...")
    
    # Manually advance time (in real: wait or check periodically)
    for addr, account in rent.accounts.items():
        for key, slot in account.slots.items():
            slot.last_rent_payment -= 10 * 86400  # 10 days ago
    
    # Check evictions
    evicted = rent.check_evictions()
    print(f"  Slots evicted: {evicted}")
    
    # Show updated status
    info1 = rent.get_storage_info("alice", "contract_storage")
    if info1:
        print(f"\n  Alice after 10 days:")
        print(f"    Rent due: {info1['rent_due']}")
        print(f"    Status: {info1['status']}")
    
    # Pay more rent
    print("\n" + "-" * 60)
    print("Alice paying more rent...")
    rent.pay_rent("alice", "contract_storage", 10000)
    
    info1 = rent.get_storage_info("alice", "contract_storage")
    if info1:
        print(f"  New balance: {info1['rent_balance']}")
        print(f"  Status: {info1['status']}")
    
    # Cost estimation
    print("\n" + "-" * 60)
    print("Cost Estimation:")
    cost_30d = rent.estimate_storage_cost(data_size=1000, days=30)
    cost_365d = rent.estimate_storage_cost(data_size=1000, days=365)
    print(f"  1KB for 30 days: {cost_30d}")
    print(f"  1KB for 365 days: {cost_365d}")
    
    # Stats
    print("\n" + "=" * 60)
    print("Network Statistics:")
    stats = rent.get_network_stats()
    print(f"  Total accounts: {stats['total_accounts']}")
    print(f"  Total storage: {stats['total_storage_bytes']} bytes")
    print(f"  Rent per day: {stats['total_rent_per_day']}")
    print(f"  Evicted slots: {stats['total_evicted_slots']}")
    
    # Comparison
    print("\n" + "-" * 60)
    print("Storage Model Comparison:")
    comparison = rent.compare_storage_models()
    
    print("\n  Traditional:")
    for k, v in comparison['traditional'].items():
        print(f"    {k}: {v}")
    
    print("\n  Rent Model:")
    for k, v in comparison['rent_model'].items():
        print(f"    {k}: {v}")
    
    print("\n" + "=" * 60)
    print("State rent: Sustainable storage through economics")
    print("=" * 60)
