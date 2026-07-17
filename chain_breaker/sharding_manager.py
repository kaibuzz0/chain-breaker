"""
sharding_manager.py

Parallel blockchain sharding for high throughput.
Splits single chain into N parallel shards, each processing independent transactions.

Key concepts:
- Shard ID: which chain handles the transaction
- Cross-shard: transactions touching multiple shards
- Beacon chain: coordinates between shards
- 64 shards = 64x throughput

Target: 1000+ TPS (vs Bitcoin's 7)
"""

import hashlib
import time
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum


@dataclass
class Shard:
    """Individual shard (parallel blockchain)."""
    shard_id: int
    chain: List[Dict] = field(default_factory=list)
    pending: List[Dict] = field(default_factory=list)
    validators: List[str] = field(default_factory=list)
    
    def height(self) -> int:
        return len(self.chain)
    
    def add_block(self, block: Dict):
        self.chain.append(block)
        self.pending = []  # Clear pending after block
    
    def add_pending(self, tx: Dict):
        self.pending.append(tx)
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            'shard_id': self.shard_id,
            'height': self.height(),
            'blocks': len(self.chain),
            'pending': len(self.pending),
            'validators': len(self.validators),
        }


class ShardingManager:
    """
    Manages parallel blockchain shards.
    
    How it works:
    1. Each address belongs to a specific shard (deterministic)
    2. Most transactions stay within one shard (fast)
    3. Cross-shard transactions need coordination (slower)
    4. Beacon chain tracks cross-shard state
    """
    
    def __init__(
        self,
        num_shards: int = 8,           # Parallel chains
        beacon_interval: int = 12,     # Seconds between beacon blocks
    ):
        self.num_shards = num_shards
        self.beacon_interval = beacon_interval
        
        # Create shards
        self.shards: Dict[int, Shard] = {
            i: Shard(shard_id=i) for i in range(num_shards)
        }
        
        # Beacon chain (coordinates cross-shard)
        self.beacon_chain: List[Dict] = []
        self.cross_shard_queue: List[Dict] = []
        
        # Stats
        self.total_tx_processed = 0
        self.cross_shard_tx_count = 0
    
    def get_shard_for_address(self, address: str) -> int:
        """
        Determine which shard an address belongs to.
        
        Deterministic: same address always same shard.
        """
        # Use first 4 chars of address hash
        hash_val = int(hashlib.sha256(address.encode()).hexdigest()[:4], 16)
        return hash_val % self.num_shards
    
    def is_cross_shard(self, from_addr: str, to_addr: str) -> bool:
        """Check if transaction crosses shards."""
        return self.get_shard_for_address(from_addr) != self.get_shard_for_address(to_addr)
    
    def route_transaction(self, tx: Dict) -> Tuple[int, Optional[int]]:
        """
        Route transaction to appropriate shard(s).
        
        Returns: (primary_shard, secondary_shard or None)
        """
        from_addr = tx.get('from', '')
        to_addr = tx.get('to', '')
        
        from_shard = self.get_shard_for_address(from_addr)
        
        if self.is_cross_shard(from_addr, to_addr):
            to_shard = self.get_shard_for_address(to_addr)
            return from_shard, to_shard
        
        return from_shard, None
    
    def submit_transaction(self, tx: Dict) -> Dict[str, Any]:
        """
        Submit transaction to sharded network.
        
        Returns routing info.
        """
        from_shard, to_shard = self.route_transaction(tx)
        
        tx['from_shard'] = from_shard
        tx['to_shard'] = to_shard
        tx['submitted_at'] = time.time()
        
        if to_shard is None:
            # Single-shard transaction (fast)
            self.shards[from_shard].add_pending(tx)
            return {
                'status': 'single_shard',
                'primary_shard': from_shard,
                'estimated_time': 'fast',
            }
        else:
            # Cross-shard (needs coordination)
            self.cross_shard_queue.append(tx)
            self.cross_shard_tx_count += 1
            return {
                'status': 'cross_shard',
                'from_shard': from_shard,
                'to_shard': to_shard,
                'estimated_time': 'slower',
            }
    
    def process_cross_shard(self) -> int:
        """
        Process queued cross-shard transactions.
        
        Called periodically by beacon chain.
        """
        processed = 0
        
        for tx in self.cross_shard_queue[:]:
            from_shard = tx.get('from_shard')
            to_shard = tx.get('to_shard')
            
            if from_shard is not None and to_shard is not None:
                # Lock on from_shard
                self.shards[from_shard].add_pending(tx)
                # Credit on to_shard (simplified)
                self.shards[to_shard].add_pending({
                    'type': 'cross_credit',
                    'original_tx': tx.get('hash'),
                    'to': tx.get('to'),
                    'amount': tx.get('amount'),
                })
                processed += 1
        
        self.cross_shard_queue = []
        return processed
    
    def produce_beacon_block(self) -> Dict:
        """
        Produce beacon block (coordinates shards).
        
        Contains references to all shard heads.
        """
        shard_heads = {}
        for shard_id, shard in self.shards.items():
            if shard.chain:
                shard_heads[shard_id] = shard.chain[-1].get('hash', '0')
        
        beacon_block = {
            'type': 'beacon',
            'height': len(self.beacon_chain),
            'timestamp': time.time(),
            'shard_heads': shard_heads,
            'num_shards': self.num_shards,
            'cross_shard_processed': self.process_cross_shard(),
        }
        
        self.beacon_chain.append(beacon_block)
        return beacon_block
    
    def get_shard_stats(self) -> List[Dict]:
        """Get stats for all shards."""
        return [shard.get_stats() for shard in self.shards.values()]
    
    def get_throughput_estimate(self) -> int:
        """
        Estimate transactions per second.
        
        Single shard: ~7 TPS (Bitcoin-like)
        With N shards: ~7*N TPS
        """
        base_tps = 7  # Per shard
        return base_tps * self.num_shards
    
    def get_network_stats(self) -> Dict[str, Any]:
        """Get overall network statistics."""
        total_blocks = sum(s.height() for s in self.shards.values())
        total_pending = sum(len(s.pending) for s in self.shards.values())
        
        return {
            'num_shards': self.num_shards,
            'beacon_height': len(self.beacon_chain),
            'total_shard_blocks': total_blocks,
            'total_pending': total_pending,
            'cross_shard_pending': len(self.cross_shard_queue),
            'estimated_tps': self.get_throughput_estimate(),
            'vs_bitcoin_tps': f"{self.get_throughput_estimate() / 7:.0f}x",
        }
    
    def get_address_location(self, address: str) -> Dict[str, Any]:
        """Get shard location info for address."""
        shard = self.get_shard_for_address(address)
        return {
            'address': address,
            'shard': shard,
            'validators': len(self.shards[shard].validators),
        }


if __name__ == "__main__":
    print("=" * 60)
    print("SHARDING MANAGER - Parallel Blockchain")
    print("=" * 60)
    
    # Create 8-shard network
    manager = ShardingManager(num_shards=8)
    
    print(f"\nNetwork: {manager.num_shards} shards")
    print(f"Base TPS per shard: ~7")
    print(f"Estimated total TPS: {manager.get_throughput_estimate()}")
    print(f"Vs Bitcoin: {manager.get_throughput_estimate() / 7:.0f}x faster")
    
    # Show address distribution
    print("\n" + "-" * 60)
    print("Address Distribution:")
    
    test_addresses = [
        "alice123", "bob456", "charlie789", "dave012",
        "eve345", "frank678", "grace901", "henry234",
    ]
    
    shard_distribution: Dict[int, List[str]] = {i: [] for i in range(8)}
    
    for addr in test_addresses:
        shard = manager.get_shard_for_address(addr)
        shard_distribution[shard].append(addr)
        print(f"  {addr}: shard {shard}")
    
    # Submit transactions
    print("\n" + "-" * 60)
    print("Submitting Transactions:")
    
    transactions = [
        {'from': 'alice123', 'to': 'bob456', 'amount': 100},      # Cross-shard
        {'from': 'alice123', 'to': 'charlie789', 'amount': 50},    # Cross-shard
        {'from': 'bob456', 'to': 'eve345', 'amount': 25},         # Same-shard (bob/eve)
        {'from': 'dave012', 'to': 'frank678', 'amount': 200},      # Same-shard
        {'from': 'grace901', 'to': 'henry234', 'amount': 75},     # Cross-shard
    ]
    
    single_shard_count = 0
    cross_shard_count = 0
    
    for tx in transactions:
        result = manager.submit_transaction(tx)
        
        if result['status'] == 'single_shard':
            single_shard_count += 1
            print(f"  ✓ {tx['from'][:8]} -> {tx['to'][:8]}: "
                  f"single-shard (shard {result['primary_shard']})")
        else:
            cross_shard_count += 1
            print(f"  ⚡ {tx['from'][:8]} -> {tx['to'][:8]}: "
                  f"cross-shard ({result['from_shard']} -> {result['to_shard']})")
    
    # Produce beacon block
    print("\n" + "-" * 60)
    print("Beacon Block:")
    beacon = manager.produce_beacon_block()
    print(f"  Height: {beacon['height']}")
    print(f"  Timestamp: {time.strftime('%H:%M:%S', time.localtime(beacon['timestamp']))}")
    print(f"  Shard heads: {len(beacon['shard_heads'])}")
    print(f"  Cross-shard processed: {beacon['cross_shard_processed']}")
    
    # Network stats
    print("\n" + "=" * 60)
    print("Network Statistics:")
    stats = manager.get_network_stats()
    print(f"  Shards: {stats['num_shards']}")
    print(f"  Beacon height: {stats['beacon_height']}")
    print(f"  Total pending: {stats['total_pending']}")
    print(f"  Cross-shard queue: {stats['cross_shard_pending']}")
    print(f"  Estimated TPS: {stats['estimated_tps']}")
    print(f"  Speedup: {stats['vs_bitcoin_tps']}")
    
    # Shard details
    print("\nShard Details:")
    for shard_stats in manager.get_shard_stats():
        print(f"  Shard {shard_stats['shard_id']}: "
              f"{shard_stats['blocks']} blocks, "
              f"{shard_stats['pending']} pending, "
              f"{shard_stats['validators']} validators")
    
    print("\n" + "=" * 60)
    print("Sharding: Parallel processing for massive scalability")
    print("=" * 60)
