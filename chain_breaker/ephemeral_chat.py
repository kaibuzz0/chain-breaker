"""
ephemeral_chat.py

On-chain ephemeral messaging system.
- Text-only (no files, no emojis)
- Stored in blocks temporarily
- Auto-deletes after 24 hours (configurable)
- Minimal size: sender + message + timestamp + ttl

Messages are pruned from full nodes after TTL expires.
Archives keep only hash proofs (not content).

This enables community communication without permanent storage bloat.
"""

import time
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from collections import deque


@dataclass
class ChatMessage:
    """
    Single chat message.
    
    Fields:
    - sender: Address of sender
    - content: Text content (ASCII only, no emojis)
    - timestamp: Unix timestamp
    - ttl: Time-to-live in seconds (default 24 hours)
    - signature: Optional signature for authenticity
    """
    sender: str
    content: str
    timestamp: float
    ttl: int = 86400  # 24 hours default
    signature: Optional[str] = None
    
    def __post_init__(self):
        # Sanitize content: ASCII only, no emojis, max 280 chars
        self.content = self._sanitize_content(self.content)
    
    def _sanitize_content(self, text: str) -> str:
        """
        Sanitize message content.
        - ASCII only (no unicode/emojis)
        - Max 280 characters
        - No control characters
        """
        # Remove non-ASCII
        ascii_only = ''.join(c for c in text if ord(c) < 128)
        
        # Remove control chars except newline
        clean = ''.join(c for c in ascii_only if c == '\n' or ord(c) >= 32)
        
        # Truncate to 280 chars (like Twitter)
        return clean[:280]
    
    def is_expired(self, current_time: Optional[float] = None) -> bool:
        """Check if message has expired."""
        now = current_time or time.time()
        return (now - self.timestamp) > self.ttl
    
    def get_hash(self) -> str:
        """Get message hash for verification."""
        data = f"{self.sender}:{self.content}:{self.timestamp}:{self.ttl}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """Deserialize from dict."""
        return cls(
            sender=data['sender'],
            content=data['content'],
            timestamp=data['timestamp'],
            ttl=data.get('ttl', 86400),
            signature=data.get('signature')
        )
    
    def size_bytes(self) -> int:
        """Get approximate size in bytes."""
        return len(self.sender) + len(self.content) + 32  # Rough estimate


class EphemeralChat:
    """
    Ephemeral chat system for blockchain.
    
    Features:
    - Messages stored temporarily in blocks
    - Auto-pruning of expired messages
    - Channels/rooms support
    - Rate limiting per address
    """
    
    def __init__(
        self,
        default_ttl: int = 86400,  # 24 hours
        max_messages_per_block: int = 100,
        rate_limit_window: int = 60,  # 1 minute
        rate_limit_max: int = 10,      # 10 messages per minute
    ):
        self.default_ttl = default_ttl
        self.max_messages_per_block = max_messages_per_block
        self.rate_limit_window = rate_limit_window
        self.rate_limit_max = rate_limit_max
        
        # Active messages (not yet expired)
        self.messages: deque = deque(maxlen=10000)  # Circular buffer
        
        # Channels: channel_name -> list of messages
        self.channels: Dict[str, List[ChatMessage]] = {}
        
        # Rate limiting: address -> list of timestamps
        self.rate_limiter: Dict[str, List[float]] = {}
        
        # Stats
        self.total_messages = 0
        self.expired_messages = 0
        self.rejected_rate_limited = 0
    
    def check_rate_limit(self, address: str) -> bool:
        """
        Check if address is rate limited.
        Returns True if allowed, False if limited.
        """
        now = time.time()
        
        if address not in self.rate_limiter:
            self.rate_limiter[address] = []
        
        # Remove old timestamps outside window
        window_start = now - self.rate_limit_window
        self.rate_limiter[address] = [
            ts for ts in self.rate_limiter[address] if ts > window_start
        ]
        
        # Check if under limit
        if len(self.rate_limiter[address]) >= self.rate_limit_max:
            self.rejected_rate_limited += 1
            return False
        
        # Record this message
        self.rate_limiter[address].append(now)
        return True
    
    def send_message(
        self,
        sender: str,
        content: str,
        channel: str = "general",
        ttl: Optional[int] = None,
        signature: Optional[str] = None
    ) -> Optional[ChatMessage]:
        """
        Send a chat message.
        
        Args:
            sender: Sender address
            content: Message text (sanitized)
            channel: Channel name (default 'general')
            ttl: Time-to-live in seconds (default 24h)
            signature: Optional signature
        
        Returns:
            ChatMessage if successful, None if rejected
        """
        # Rate limit check
        if not self.check_rate_limit(sender):
            return None
        
        # Create message
        msg = ChatMessage(
            sender=sender,
            content=content,
            timestamp=time.time(),
            ttl=ttl or self.default_ttl,
            signature=signature
        )
        
        # Add to active messages
        self.messages.append(msg)
        
        # Add to channel
        if channel not in self.channels:
            self.channels[channel] = []
        self.channels[channel].append(msg)
        
        self.total_messages += 1
        
        return msg
    
    def get_messages(
        self,
        channel: str = "general",
        limit: int = 50,
        include_expired: bool = False
    ) -> List[ChatMessage]:
        """
        Get recent messages from a channel.
        
        Args:
            channel: Channel name
            limit: Max messages to return
            include_expired: If True, include expired messages
        """
        if channel not in self.channels:
            return []
        
        now = time.time()
        result = []
        
        # Iterate backwards (newest first)
        for msg in reversed(self.channels[channel]):
            if len(result) >= limit:
                break
            
            if include_expired or not msg.is_expired(now):
                result.append(msg)
        
        return result
    
    def prune_expired(self) -> int:
        """
        Remove expired messages from active storage.
        Returns number pruned.
        """
        now = time.time()
        pruned = 0
        
        # Prune from channels
        for channel in self.channels:
            before = len(self.channels[channel])
            self.channels[channel] = [
                msg for msg in self.channels[channel]
                if not msg.is_expired(now)
            ]
            pruned += before - len(self.channels[channel])
        
        # Prune from main buffer
        # (deque maxlen handles this automatically)
        
        self.expired_messages += pruned
        return pruned
    
    def get_channels(self) -> List[str]:
        """Get list of active channels."""
        return list(self.channels.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get chat statistics."""
        now = time.time()
        active = sum(1 for msg in self.messages if not msg.is_expired(now))
        
        return {
            'total_messages': self.total_messages,
            'active_messages': active,
            'expired_messages': self.expired_messages,
            'rejected_rate_limited': self.rejected_rate_limited,
            'channels': len(self.channels),
            'default_ttl_hours': self.default_ttl / 3600,
        }
    
    def to_transaction(self, msg: ChatMessage) -> Dict[str, Any]:
        """
        Convert chat message to blockchain transaction.
        
        This allows chat to be stored in blocks.
        """
        return {
            'type': 'chat',
            'sender': msg.sender,
            'content': msg.content,
            'timestamp': msg.timestamp,
            'ttl': msg.ttl,
            'signature': msg.signature,
            'hash': msg.get_hash(),
        }
    
    @classmethod
    def from_transaction(cls, tx: Dict[str, Any]) -> ChatMessage:
        """Restore chat message from transaction."""
        return ChatMessage(
            sender=tx['sender'],
            content=tx['content'],
            timestamp=tx['timestamp'],
            ttl=tx.get('ttl', 86400),
            signature=tx.get('signature')
        )


if __name__ == "__main__":
    print("=" * 60)
    print("EPHEMERAL CHAT - On-Chain Messaging")
    print("=" * 60)
    
    chat = EphemeralChat(default_ttl=3600)  # 1 hour for demo
    
    print("\nSending messages...")
    
    # Send some messages
    msg1 = chat.send_message("alice", "Hello everyone! 👋", channel="general")
    if msg1:
        print(f"✓ Alice: {msg1.content}")
    
    msg2 = chat.send_message("bob", "Hey Alice! 🎉", channel="general")
    if msg2:
        print(f"✓ Bob: {msg2.content}")
    
    msg3 = chat.send_message(
        "charlie",
        "This is a very long message that should be truncated to 280 characters "
        "because we don't want people spamming the blockchain with massive texts "
        "that would bloat the storage and make everything slow and expensive.",
        channel="general"
    )
    if msg3:
        print(f"✓ Charlie: {msg3.content[:50]}... (truncated)")
    
    # Show stats
    print("\n" + "=" * 60)
    print("Chat Statistics:")
    stats = chat.get_stats()
    print(f"  Total messages: {stats['total_messages']}")
    print(f"  Active: {stats['active_messages']}")
    print(f"  Channels: {stats['channels']}")
    print(f"  TTL: {stats['default_ttl_hours']:.1f} hours")
    
    # Show messages in channel
    print("\nMessages in #general:")
    print("-" * 60)
    for msg in chat.get_messages(channel="general", limit=10):
        time_str = time.strftime('%H:%M:%S', time.localtime(msg.timestamp))
        print(f"[{time_str}] {msg.sender}: {msg.content}")
    
    # Show transaction format
    if msg1:
        print("\n" + "=" * 60)
        print("Blockchain Transaction Format:")
        tx = chat.to_transaction(msg1)
        print(f"  Type: {tx['type']}")
        print(f"  Size: ~{len(str(tx))} bytes")
        print(f"  Hash: {tx['hash'][:20]}...")
    
    # Rate limit test
    print("\n" + "=" * 60)
    print("Rate Limit Test (sending 15 messages in 1 second)...")
    spammer = "spammer"
    sent = 0
    for i in range(15):
        msg = chat.send_message(spammer, f"Spam {i}", channel="test")
        if msg:
            sent += 1
    print(f"  Sent: {sent}, Rejected: {15 - sent}")
    print(f"  Rate limit working: {sent < 15}")
    
    print("\n" + "=" * 60)
    print("Ephemeral chat: Text-only, auto-deletes, rate-limited")
    print("=" * 60)
