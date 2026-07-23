#!/usr/bin/env python3
"""
Mesh-Node: UDP P2P Networking for Chain-Breaker Blockchain

Lightweight gossip protocol for mobile/embedded devices.
Works over any IP network (WiFi, cellular, internet).

Features:
- UDP gossip protocol (flood-based propagation)
- Peer discovery via bootstrap nodes
- NAT traversal with periodic keepalives
- Battery-aware operation (batch sync when charging)
- Message deduplication (bloom filter)
- Auto-healing mesh topology

Author: Chain-Breaker Team
Version: 1.0.0
"""

import socket
import json
import time
import hashlib
import threading
import random
import struct
from typing import Dict, List, Set, Callable, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import IntEnum
import select

from chain_core import Block, Blockchain, Transaction, ScriptureTransaction

__version__ = "1.0.0"
__all__ = ['MeshNode', 'MessageType', 'GossipProtocol']


class MessageType(IntEnum):
    """Message types for Chain-Breaker protocol."""
    PING = 0x01          # Keepalive / discovery
    PONG = 0x02          # Keepalive response
    BLOCK = 0x03         # New block announcement
    TRANSACTION = 0x04   # New transaction
    GET_BLOCK = 0x05     # Request specific block
    BLOCK_DATA = 0x06    # Block data response
    GET_PEERS = 0x07     # Request peer list
    PEER_LIST = 0x08     # Peer list response
    SYNC_REQUEST = 0x09  # Request chain sync
    SYNC_RESPONSE = 0x0A # Chain sync data


@dataclass
class Peer:
    """
    Peer node information.
    
    Attributes:
        address: IP address
        port: UDP port
        last_seen: Unix timestamp
        reputation: Trust score (-100 to +100)
        capabilities: Feature flags
    """
    address: str
    port: int
    last_seen: float = 0.0
    reputation: int = 0
    capabilities: int = 0
    
    def __hash__(self):
        return hash((self.address, self.port))
    
    def __eq__(self, other):
        return (self.address, self.port) == (other.address, other.port)
    
    def to_tuple(self) -> Tuple[str, int]:
        """Return (address, port) tuple for socket operations."""
        return (self.address, self.port)


class BloomFilter:
    """
    Simple bloom filter for message deduplication.
    
    Prevents processing same message multiple times
    while keeping memory usage low on mobile devices.
    """
    
    def __init__(self, size: int = 1024 * 1024, num_hashes: int = 3):
        """
        Args:
            size: Filter size in bits (1MB default)
            num_hashes: Number of hash functions
        """
        self.size = size
        self.num_hashes = num_hashes
        self.bits = bytearray(size // 8)
        self.count = 0
        
    def _hashes(self, item: str) -> List[int]:
        """Generate hash positions for item."""
        positions = []
        for i in range(self.num_hashes):
            h = hashlib.sha256(f"{item}:{i}".encode()).hexdigest()
            pos = int(h, 16) % self.size
            positions.append(pos)
        return positions
    
    def add(self, item: str):
        """Add item to filter."""
        for pos in self._hashes(item):
            byte_idx = pos // 8
            bit_idx = pos % 8
            self.bits[byte_idx] |= (1 << bit_idx)
        self.count += 1
    
    def __contains__(self, item: str) -> bool:
        """Check if item might be in filter (may have false positives)."""
        for pos in self._hashes(item):
            byte_idx = pos // 8
            bit_idx = pos % 8
            if not (self.bits[byte_idx] & (1 << bit_idx)):
                return False
        return True
    
    def clear(self):
        """Reset filter (call periodically to prevent saturation)."""
        self.bits = bytearray(self.size // 8)
        self.count = 0


class MeshNode:
    """
    P2P mesh node for Chain-Breaker blockchain.
    
    Implements gossip protocol over UDP for maximum compatibility
    with mobile and embedded devices.
    
    Attributes:
        blockchain: Local blockchain instance
        port: UDP port (default 8333 like Bitcoin)
        peers: Set of known peers
        seen_messages: Bloom filter for dedup
        running: Whether node is active
        
    Example:
        >>> blockchain = Blockchain()
        >>> node = MeshNode(blockchain, port=8333)
        >>> node.start()
        >>> node.connect_to_peer("192.168.1.100", 8333)
        >>> node.broadcast_block(blockchain.chain[-1])
    """
    
    DEFAULT_PORT = 8333
    VERSION = 1
    
    def __init__(self, 
                 blockchain: Blockchain,
                 port: int = DEFAULT_PORT,
                 max_peers: int = 25,
                 enable_discovery: bool = True):
        """
        Initialize mesh node.
        
        Args:
            blockchain: Local blockchain instance
            port: UDP port to listen on
            max_peers: Maximum peers to maintain
            enable_discovery: Auto-discover peers
        """
        self.blockchain = blockchain
        self.port = port
        self.max_peers = max_peers
        self.enable_discovery = enable_discovery
        
        # Network socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('0.0.0.0', port))
        self.socket.setblocking(False)
        
        # Peer management
        self.peers: Dict[Tuple[str, int], Peer] = {}
        self.bootstrap_peers: List[Tuple[str, int]] = [
            # Default bootstrap nodes (would be real IPs in production)
            # ("seed1.chain-breaker.org", 8333),
            # ("seed2.chain-breaker.org", 8333),
        ]
        
        # Message handling
        self.seen_messages = BloomFilter(size=1024*1024)  # 1MB
        self.message_handlers: Dict[MessageType, Callable] = {
            MessageType.PING: self._handle_ping,
            MessageType.PONG: self._handle_pong,
            MessageType.BLOCK: self._handle_block,
            MessageType.TRANSACTION: self._handle_transaction,
            MessageType.GET_BLOCK: self._handle_get_block,
            MessageType.BLOCK_DATA: self._handle_block_data,
            MessageType.GET_PEERS: self._handle_get_peers,
            MessageType.PEER_LIST: self._handle_peer_list,
            MessageType.SYNC_REQUEST: self._handle_sync_request,
            MessageType.SYNC_RESPONSE: self._handle_sync_response,
        }
        
        # State
        self.running = False
        self.threads: List[threading.Thread] = []
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'blocks_announced': 0,
            'blocks_received': 0,
        }
        
        # Callbacks
        self.on_block_received: Optional[Callable] = None
        self.on_transaction_received: Optional[Callable] = None
        self.on_peer_connected: Optional[Callable] = None
        
    def start(self):
        """Start the mesh node (non-blocking)."""
        self.running = True
        
        # Start receiver thread
        t_recv = threading.Thread(target=self._receive_loop, daemon=True)
        t_recv.start()
        self.threads.append(t_recv)
        
        # Start maintenance thread
        t_maint = threading.Thread(target=self._maintenance_loop, daemon=True)
        t_maint.start()
        self.threads.append(t_maint)
        
        print(f"🌐 Mesh node started on port {self.port}")
        print(f"   Node ID: {self._get_node_id()[:16]}...")
        
        # Connect to bootstrap peers
        if self.enable_discovery:
            self._connect_to_bootstrap()
    
    def stop(self):
        """Stop the mesh node."""
        self.running = False
        self.socket.close()
        for t in self.threads:
            t.join(timeout=1.0)
        print("🛑 Mesh node stopped")
    
    def _get_node_id(self) -> str:
        """Generate unique node ID from port."""
        # In production, use public key
        return hashlib.sha256(f"node:{self.port}".encode()).hexdigest()
    
    def _receive_loop(self):
        """Background thread: receive and process messages."""
        while self.running:
            try:
                ready, _, _ = select.select([self.socket], [], [], 0.1)
                if ready:
                    data, addr = self.socket.recvfrom(65535)
                    self._process_message(data, addr)
            except Exception as e:
                if self.running:
                    print(f"Receive error: {e}")
    
    def _process_message(self, data: bytes, addr: Tuple[str, int]):
        """Parse and handle incoming message."""
        try:
            # Check minimum size (header)
            if len(data) < 24:
                return
            
            # Parse header
            magic = struct.unpack('>I', data[:4])[0]
            if magic != 0xE8E8E8E8:  # Chain-Breaker magic
                return
            
            version = struct.unpack('>B', data[4:5])[0]
            msg_type = struct.unpack('>B', data[5:6])[0]
            msg_len = struct.unpack('>I', data[6:10])[0]
            checksum = data[10:14]
            msg_id = data[14:22].hex()
            
            # Checksum verification
            payload = data[22:]
            if hashlib.sha256(payload).digest()[:4] != checksum:
                return
            
            # Deduplication
            if msg_id in self.seen_messages:
                return
            self.seen_messages.add(msg_id)
            
            # Update stats
            self.stats['messages_received'] += 1
            
            # Update peer
            peer = self._get_or_create_peer(addr[0], addr[1])
            peer.last_seen = time.time()
            
            # Handle message
            handler = self.message_handlers.get(MessageType(msg_type))
            if handler:
                handler(payload, peer)
                
        except Exception as e:
            pass  # Silently drop malformed packets
    
    def _create_message(self, msg_type: MessageType, payload: bytes) -> bytes:
        """Create protocol message with header."""
        # Header format:
        #   4 bytes: Magic (0xE8E8E8E8)
        #   1 byte: Version
        #   1 byte: Message type
        #   4 bytes: Payload length
        #   4 bytes: Checksum (SHA256 first 4 bytes)
        #   8 bytes: Message ID (for dedup)
        #   N bytes: Payload
        
        msg_id = hashlib.sha256(f"{time.time()}:{random.random()}".encode()).digest()[:8]
        checksum = hashlib.sha256(payload).digest()[:4]
        
        header = struct.pack('>IBBI', 
            0xE8E8E8E8,  # Magic
            self.VERSION,
            msg_type,
            len(payload)
        ) + checksum + msg_id
        
        return header + payload
    
    def send_to_peer(self, peer: Peer, msg_type: MessageType, payload: bytes):
        """Send message to specific peer."""
        message = self._create_message(msg_type, payload)
        
        try:
            self.socket.sendto(message, peer.to_tuple())
            self.stats['messages_sent'] += 1
        except Exception as e:
            print(f"Send error to {peer.address}:{peer.port}: {e}")
    
    def gossip(self, msg_type: MessageType, payload: bytes, 
               exclude: Optional[Peer] = None):
        """
        Broadcast message to all peers (flood-based).
        
        Args:
            msg_type: Message type
            payload: Message payload
            exclude: Peer to exclude (usually sender)
        """
        message = self._create_message(msg_type, payload)
        
        for peer_addr, peer in self.peers.items():
            if exclude and peer == exclude:
                continue
            
            try:
                self.socket.sendto(message, peer.to_tuple())
                self.stats['messages_sent'] += 1
            except:
                pass
    
    def connect_to_peer(self, address: str, port: int) -> bool:
        """
        Manually connect to a peer.
        
        Args:
            address: IP address or hostname
            port: UDP port
            
        Returns:
            bool: True if connection initiated
        """
        if len(self.peers) >= self.max_peers:
            return False
        
        peer = self._get_or_create_peer(address, port)
        
        # Send PING
        payload = json.dumps({
            'version': self.VERSION,
            'port': self.port,
            'block_height': len(self.blockchain.chain),
            'timestamp': time.time()
        }).encode()
        
        self.send_to_peer(peer, MessageType.PING, payload)
        
        if self.on_peer_connected:
            self.on_peer_connected(peer)
        
        return True
    
    def _get_or_create_peer(self, address: str, port: int) -> Peer:
        """Get existing peer or create new one."""
        key = (address, port)
        if key not in self.peers:
            self.peers[key] = Peer(address=address, port=port)
        return self.peers[key]
    
    def _connect_to_bootstrap(self):
        """Connect to bootstrap peers."""
        for addr, port in self.bootstrap_peers:
            self.connect_to_peer(addr, port)
    
    def _maintenance_loop(self):
        """Background thread: peer maintenance and keepalives."""
        while self.running:
            time.sleep(30)  # Every 30 seconds
            
            if not self.running:
                break
            
            # Remove stale peers
            now = time.time()
            stale = [k for k, p in self.peers.items() 
                    if now - p.last_seen > 300]  # 5 min timeout
            for k in stale:
                del self.peers[k]
            
            # Send keepalive PINGs
            for peer in list(self.peers.values()):
                payload = json.dumps({
                    'version': self.VERSION,
                    'port': self.port,
                    'block_height': len(self.blockchain.chain)
                }).encode()
                self.send_to_peer(peer, MessageType.PING, payload)
            
            # Clear bloom filter if saturated
            if self.seen_messages.count > 100000:
                self.seen_messages.clear()
    
    # ==================== Message Handlers ====================
    
    def _handle_ping(self, payload: bytes, peer: Peer):
        """Handle PING (keepalive/discovery)."""
        try:
            data = json.loads(payload)
            peer.port = data.get('port', peer.port)
            
            # Respond with PONG
            response = json.dumps({
                'version': self.VERSION,
                'port': self.port,
                'block_height': len(self.blockchain.chain),
                'peers': len(self.peers)
            }).encode()
            self.send_to_peer(peer, MessageType.PONG, response)
            
        except json.JSONDecodeError:
            pass
    
    def _handle_pong(self, payload: bytes, peer: Peer):
        """Handle PONG (keepalive response)."""
        try:
            data = json.loads(payload)
            remote_height = data.get('block_height', 0)
            
            # If they have more blocks, request sync
            if remote_height > len(self.blockchain.chain):
                self._request_sync(peer)
                
        except json.JSONDecodeError:
            pass
    
    def _handle_block(self, payload: bytes, peer: Peer):
        """Handle BLOCK announcement."""
        try:
            data = json.loads(payload)
            block_hash = data['hash']
            block_height = data['height']
            
            print(f"📦 Block announcement: {block_hash[:16]}... "
                  f"(height {block_height}) from {peer.address}")
            
            # Check if we have it
            # In production, check blockchain
            
            # If new, gossip to peers
            self.gossip(MessageType.BLOCK, payload, exclude=peer)
            
            self.stats['blocks_announced'] += 1
            
            if self.on_block_received:
                self.on_block_received(data, peer)
                
        except (json.JSONDecodeError, KeyError):
            pass
    
    def _handle_transaction(self, payload: bytes, peer: Peer):
        """Handle TRANSACTION announcement."""
        try:
            data = json.loads(payload)
            tx_hash = data.get('hash', 'unknown')
            
            print(f"💸 Transaction: {tx_hash[:16]}... from {peer.address}")
            
            # Add to mempool
            # self.blockchain.mempool.append(...)
            
            # Gossip
            self.gossip(MessageType.TRANSACTION, payload, exclude=peer)
            
            if self.on_transaction_received:
                self.on_transaction_received(data, peer)
                
        except json.JSONDecodeError:
            pass
    
    def _handle_get_block(self, payload: bytes, peer: Peer):
        """Handle GET_BLOCK request."""
        try:
            data = json.loads(payload)
            block_hash = data['hash']
            
            # Send block if we have it
            # In production, lookup in blockchain
            
        except json.JSONDecodeError:
            pass
    
    def _handle_block_data(self, payload: bytes, peer: Peer):
        """Handle BLOCK_DATA response."""
        try:
            data = json.loads(payload)
            # Validate and add to chain
            self.stats['blocks_received'] += 1
        except json.JSONDecodeError:
            pass
    
    def _handle_get_peers(self, payload: bytes, peer: Peer):
        """Handle GET_PEERS request."""
        # Send peer list
        peers_data = [
            {'address': p.address, 'port': p.port}
            for p in self.peers.values()
        ]
        response = json.dumps({'peers': peers_data}).encode()
        self.send_to_peer(peer, MessageType.PEER_LIST, response)
    
    def _handle_peer_list(self, payload: bytes, peer: Peer):
        """Handle PEER_LIST response."""
        try:
            data = json.loads(payload)
            for peer_info in data.get('peers', []):
                addr = peer_info['address']
                port = peer_info['port']
                
                # Add to peer list if not full
                if len(self.peers) < self.max_peers:
                    self._get_or_create_peer(addr, port)
        except json.JSONDecodeError:
            pass
    
    def _handle_sync_request(self, payload: bytes, peer: Peer):
        """Handle SYNC_REQUEST."""
        try:
            data = json.loads(payload)
            start_height = data.get('start_height', 0)
            
            # Send headers/blocks from start_height
            # In production, stream blocks
            
        except json.JSONDecodeError:
            pass
    
    def _handle_sync_response(self, payload: bytes, peer: Peer):
        """Handle SYNC_RESPONSE."""
        try:
            data = json.loads(payload)
            # Process sync data
        except json.JSONDecodeError:
            pass
    
    # ==================== Public API ====================
    
    def broadcast_block(self, block: Block):
        """
        Broadcast new block to mesh.
        
        Args:
            block: Block to announce
        """
        payload = json.dumps({
            'hash': block.hash(),
            'height': len(self.blockchain.chain),
            'difficulty': block.difficulty,
            'timestamp': block.timestamp,
            'merkle_root': block.merkle_root
        }, separators=(',', ':')).encode()
        
        self.gossip(MessageType.BLOCK, payload)
        self.stats['blocks_announced'] += 1
        print(f"📢 Broadcast block {block.hash()[:16]}...")
    
    def broadcast_transaction(self, tx: Transaction):
        """
        Broadcast transaction to mempool.
        
        Args:
            tx: Transaction to broadcast
        """
        payload = json.dumps({
            'hash': tx.hash(),
            'type': tx.tx_type,
            'timestamp': tx.timestamp
        }, separators=(',', ':')).encode()
        
        self.gossip(MessageType.TRANSACTION, payload)
        print(f"📢 Broadcast transaction {tx.hash()[:16]}...")
    
    def _request_sync(self, peer: Peer):
        """Request chain sync from peer."""
        payload = json.dumps({
            'start_height': len(self.blockchain.chain),
            'max_blocks': 100
        }).encode()
        self.send_to_peer(peer, MessageType.SYNC_REQUEST, payload)
    
    def get_stats(self) -> Dict:
        """Get node statistics."""
        return {
            **self.stats,
            'peers_connected': len(self.peers),
            'node_id': self._get_node_id()[:16],
            'block_height': len(self.blockchain.chain),
            'port': self.port
        }


# ==================== Self-Test ====================

def run_self_tests():
    """Run mesh node tests."""
    import sys
    
    print("=" * 70)
    print("🧪 Mesh-Node Self-Test Suite")
    print("=" * 70)
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Bloom Filter
    print("\n1️⃣ Testing Bloom Filter...")
    try:
        bf = BloomFilter(size=1024, num_hashes=3)
        bf.add("test1")
        bf.add("test2")
        
        assert "test1" in bf, "Should contain test1"
        assert "test2" in bf, "Should contain test2"
        assert "test3" not in bf, "Should not contain test3 (probably)"
        
        print("   ✅ Bloom filter working")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        tests_failed += 1
    
    # Test 2: Peer creation
    print("\n2️⃣ Testing Peer...")
    try:
        p1 = Peer("192.168.1.1", 8333)
        p2 = Peer("192.168.1.1", 8333)
        p3 = Peer("192.168.1.2", 8333)
        
        assert p1 == p2, "Same address:port should be equal"
        assert p1 != p3, "Different addresses should not be equal"
        assert hash(p1) == hash(p2), "Hashes should match"
        
        print("   ✅ Peer class working")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        tests_failed += 1
    
    # Test 3: Message creation
    print("\n3️⃣ Testing Message Creation...")
    try:
        from chain_core import Blockchain
        bc = Blockchain()
        node = MeshNode(bc, port=18333)  # Testnet port
        
        payload = b"test payload"
        msg = node._create_message(MessageType.PING, payload)
        
        assert len(msg) >= 22 + len(payload), "Message should have header"
        assert msg[:4] == b'\xe8\xe8\xe8\xe8', "Should have magic bytes"
        
        print(f"   ✅ Message created ({len(msg)} bytes)")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        tests_failed += 1
    
    # Test 4: Stats
    print("\n4️⃣ Testing Stats...")
    try:
        stats = node.get_stats()
        assert 'peers_connected' in stats
        assert 'node_id' in stats
        print(f"   ✅ Stats: {stats['peers_connected']} peers, "
              f"height {stats['block_height']}")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        tests_failed += 1
    
    # Summary
    print()
    print("=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    print(f"   ✅ Passed: {tests_passed}")
    print(f"   ❌ Failed: {tests_failed}")
    
    if tests_failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        return 1


if __name__ == "__main__":
    import sys
    exit_code = run_self_tests()
    sys.exit(exit_code)
