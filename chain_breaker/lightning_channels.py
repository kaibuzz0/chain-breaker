"""
lightning_channels.py

Off-chain payment channels for instant, cheap transactions.
Based on Bitcoin Lightning Network.

Key concepts:
- Open channel: Lock funds in multi-sig contract
- Off-chain updates: Update balances without blockchain
- Close channel: Settle final balances on-chain
- Multi-hop: Route payments through network

Benefits:
- Instant (no block confirmation)
- Cheap (no on-chain fees for updates)
- Scalable (millions of TPS off-chain)
"""

import hashlib
import secrets
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ChannelState(Enum):
    """Payment channel states."""
    OPENING = "opening"       # Funding transaction pending
    OPEN = "open"             # Active, can send/receive
    CLOSING = "closing"       # Close initiated
    CLOSED = "closed"         # Finalized on-chain
    FORCE_CLOSE = "force_close"  # Uncooperative close


@dataclass
class ChannelUpdate:
    """Single off-chain state update."""
    update_number: int
    balances: Dict[str, int]  # Address -> amount
    hash_lock: Optional[str] = None  # For HTLC routing
    signature_a: Optional[str] = None
    signature_b: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class LightningChannel:
    """Payment channel between two parties."""
    channel_id: str
    party_a: str
    party_b: str
    capacity: int               # Total locked funds
    
    # Current state
    state: ChannelState = ChannelState.OPENING
    current_update: int = 0
    updates: List[ChannelUpdate] = field(default_factory=list)
    
    # For multi-hop routing
    routing_nodes: List[str] = field(default_factory=list)
    
    def get_balance(self, party: str) -> int:
        """Get current balance for party."""
        if not self.updates:
            return 0
        return self.updates[-1].balances.get(party, 0)
    
    def update_balances(self, new_balances: Dict[str, int], update_num: int):
        """Add new state update."""
        update = ChannelUpdate(
            update_number=update_num,
            balances=new_balances.copy(),
        )
        self.updates.append(update)
        self.current_update = update_num


class LightningNetwork:
    """
    Layer 2 payment channel network.
    
    Enables instant, cheap, off-chain payments.
    """
    
    def __init__(
        self,
        min_channel_size: int = 1000,
        max_channel_size: int = 1000000,
        default_timelock: int = 3600,  # 1 hour
    ):
        self.min_channel = min_channel_size
        self.max_channel = max_channel_size
        self.default_timelock = default_timelock
        
        # Channels
        self.channels: Dict[str, LightningChannel] = {}
        self.channels_by_party: Dict[str, List[str]] = {}
        
        # Routing
        self.routing_table: Dict[str, Dict[str, str]] = {}  # Graph
        
        # Stats
        self.total_channels = 0
        self.total_offchain_tx = 0
        self.total_volume = 0
    
    def open_channel(
        self,
        party_a: str,
        party_b: str,
        capacity: int,
        initial_balance_a: int,
    ) -> Optional[str]:
        """
        Open payment channel.
        
        Locks funds on-chain, enables off-chain updates.
        """
        if not (self.min_channel <= capacity <= self.max_channel):
            return None
        
        if initial_balance_a > capacity:
            return None
        
        # Generate channel ID
        channel_id = hashlib.sha256(
            f"{party_a}:{party_b}:{time.time()}".encode()
        ).hexdigest()[:16]
        
        # Initial state
        initial_balances = {
            party_a: initial_balance_a,
            party_b: capacity - initial_balance_a,
        }
        
        channel = LightningChannel(
            channel_id=channel_id,
            party_a=party_a,
            party_b=party_b,
            capacity=capacity,
            state=ChannelState.OPEN,
        )
        
        # Initial update
        channel.update_balances(initial_balances, 0)
        
        self.channels[channel_id] = channel
        self.total_channels += 1
        
        # Index by party
        for party in [party_a, party_b]:
            if party not in self.channels_by_party:
                self.channels_by_party[party] = []
            self.channels_by_party[party].append(channel_id)
        
        return channel_id
    
    def update_channel(
        self,
        channel_id: str,
        new_balance_a: int,
        new_balance_b: int,
    ) -> bool:
        """
        Update channel balances off-chain.
        
        Instant, free, no blockchain confirmation.
        """
        if channel_id not in self.channels:
            return False
        
        channel = self.channels[channel_id]
        
        if channel.state != ChannelState.OPEN:
            return False
        
        # Verify total conserved
        if new_balance_a + new_balance_b != channel.capacity:
            return False
        
        # New update number
        new_update_num = channel.current_update + 1
        
        # Create update
        new_balances = {
            channel.party_a: new_balance_a,
            channel.party_b: new_balance_b,
        }
        
        channel.update_balances(new_balances, new_update_num)
        self.total_offchain_tx += 1
        
        return True
    
    def send_payment(
        self,
        channel_id: str,
        sender: str,
        amount: int,
    ) -> bool:
        """
        Send payment through channel.
        
        Updates balances off-chain.
        """
        if channel_id not in self.channels:
            return False
        
        channel = self.channels[channel_id]
        
        if channel.state != ChannelState.OPEN:
            return False
        
        current_balances = channel.updates[-1].balances
        
        if current_balances.get(sender, 0) < amount:
            return False  # Insufficient balance
        
        # Calculate new balances
        receiver = channel.party_b if sender == channel.party_a else channel.party_a
        
        new_balances = current_balances.copy()
        new_balances[sender] -= amount
        new_balances[receiver] = new_balances.get(receiver, 0) + amount
        
        # Apply update
        result = self.update_channel(
            channel_id,
            new_balances[channel.party_a],
            new_balances[channel.party_b],
        )
        
        if result:
            self.total_volume += amount
        
        return result
    
    def find_route(
        self,
        sender: str,
        receiver: str,
        amount: int,
    ) -> Optional[List[str]]:
        """
        Find multi-hop route for payment.
        
        Returns list of channel IDs forming path.
        """
        # Simple BFS for demo
        if sender == receiver:
            return []
        
        visited = {sender}
        queue = [(sender, [])]
        
        while queue:
            current, path = queue.pop(0)
            
            if current == receiver:
                return path
            
            # Get channels for current node
            channel_ids = self.channels_by_party.get(current, [])
            
            for chan_id in channel_ids:
                channel = self.channels.get(chan_id)
                if not channel or channel.state != ChannelState.OPEN:
                    continue
                
                # Find other party
                other = channel.party_b if current == channel.party_a else channel.party_a
                
                # Check capacity
                if channel.get_balance(current) >= amount and other not in visited:
                    visited.add(other)
                    queue.append((other, path + [chan_id]))
        
        return None  # No route found
    
    def close_channel(
        self,
        channel_id: str,
        party: str,
    ) -> Optional[Dict[str, int]]:
        """
        Close channel and settle on-chain.
        
        Returns final balances to settle.
        """
        if channel_id not in self.channels:
            return None
        
        channel = self.channels[channel_id]
        
        if channel.state == ChannelState.CLOSED:
            return None
        
        channel.state = ChannelState.CLOSING
        
        # Get final balances
        if channel.updates:
            final_balances = channel.updates[-1].balances
        else:
            final_balances = {channel.party_a: 0, channel.party_b: 0}
        
        channel.state = ChannelState.CLOSED
        
        return final_balances
    
    def get_channel(self, channel_id: str) -> Optional[LightningChannel]:
        """Get channel by ID."""
        return self.channels.get(channel_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Lightning Network statistics."""
        open_channels = sum(
            1 for c in self.channels.values()
            if c.state == ChannelState.OPEN
        )
        
        total_capacity = sum(
            c.capacity for c in self.channels.values()
            if c.state == ChannelState.OPEN
        )
        
        return {
            'total_channels': self.total_channels,
            'open_channels': open_channels,
            'total_offchain_tx': self.total_offchain_tx,
            'total_volume': self.total_volume,
            'total_capacity': total_capacity,
            'avg_channel_size': (
                total_capacity / open_channels if open_channels > 0 else 0
            ),
        }


if __name__ == "__main__":
    print("=" * 60)
    print("LIGHTNING CHANNELS - Layer 2 Payment Network")
    print("=" * 60)
    
    # Create network
    ln = LightningNetwork()
    
    print("\nOpening channels...")
    
    # Alice -> Bob
    ch1 = ln.open_channel("alice", "bob", capacity=10000, initial_balance_a=6000)
    assert ch1 is not None, "Should open channel"
    print(f"  Alice-Bob: {ch1[:8]}... (capacity: 10000)")
    
    # Bob -> Charlie
    ch2 = ln.open_channel("bob", "charlie", capacity=8000, initial_balance_a=4000)
    assert ch2 is not None, "Should open channel"
    print(f"  Bob-Charlie: {ch2[:8]}... (capacity: 8000)")
    
    # Send off-chain payments
    print("\nOff-chain payments (instant, no fees):")
    
    # Alice sends to Bob
    ln.send_payment(ch1, "alice", 1000)
    print(f"  Alice -> Bob: 1000")
    
    # Bob sends to Charlie
    ln.send_payment(ch2, "bob", 500)
    print(f"  Bob -> Charlie: 500")
    
    # Alice sends to Bob again
    ln.send_payment(ch1, "alice", 2000)
    print(f"  Alice -> Bob: 2000")
    
    # Check balances
    print("\nChannel balances:")
    for ch_id in [ch1, ch2]:
        ch = ln.get_channel(ch_id)
        print(f"  {ch.party_a[:6]} -> {ch.party_b[:6]}: "
              f"{ch.get_balance(ch.party_a)} / {ch.get_balance(ch.party_b)}")
    
    # Multi-hop routing demo
    print("\n" + "-" * 60)
    print("Multi-hop routing (Alice -> Charlie via Bob):")
    
    route = ln.find_route("alice", "charlie", 500)
    if route:
        print(f"  Route found: {' -> '.join([r[:6] for r in route])}")
    else:
        print("  No route found (direct Alice-Charlie channel needed)")
    
    # Close channels
    print("\n" + "-" * 60)
    print("Closing channels (settling on-chain):")
    
    final1 = ln.close_channel(ch1, "alice")
    print(f"  Alice-Bob final: {final1}")
    
    final2 = ln.close_channel(ch2, "bob")
    print(f"  Bob-Charlie final: {final2}")
    
    # Stats
    print("\n" + "=" * 60)
    print("Lightning Network Statistics:")
    stats = ln.get_stats()
    print(f"  Total channels: {stats['total_channels']}")
    print(f"  Off-chain transactions: {stats['total_offchain_tx']}")
    print(f"  Total volume: {stats['total_volume']}")
    print(f"  Avg channel size: {stats['avg_channel_size']:.0f}")
    
    print("\n" + "=" * 60)
    print("Lightning: Instant payments, millions TPS potential")
    print("=" * 60)
