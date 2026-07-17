"""
micro_node.py

Minimal P2P node for resource-constrained devices.
- Lightweight UDP-based discovery
- TCP for block/transaction sync
- Asyncio for efficiency
- ~100 lines, mobile-optimized

Target: Raspberry Pi 4 can run full node with <50MB RAM.
"""

import asyncio
import json
import hashlib
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Peer:
    """Peer information."""
    address: str  # IP:port
    last_seen: float
    height: int
    capabilities: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'address': self.address,
            'last_seen': self.last_seen,
            'height': self.height,
            'capabilities': self.capabilities,
        }


class MicroNode:
    """
    Minimal blockchain node for Pi/mobile deployment.
    
    Features:
    - UDP discovery (broadcast presence)
    - TCP sync (blocks, transactions)
    - Memory-efficient (no full history)
    - Async (handles many peers)
    """
    
    PROTOCOL_VERSION = 1
    DISCOVERY_PORT = 12345
    SYNC_PORT = 12346
    
    def __init__(
        self,
        node_id: Optional[str] = None,
        listen_addr: str = "0.0.0.0",
        bootstrap_peers: Optional[List[str]] = None,
    ):
        self.node_id = node_id or self._generate_node_id()
        self.listen_addr = listen_addr
        self.port = self.SYNC_PORT
        
        # Peer management
        self.peers: Dict[str, Peer] = {}
        self.max_peers = 10  # Keep low for mobile
        
        # Message handlers
        self.handlers: Dict[str, Callable] = {}
        
        # Stats
        self.messages_sent = 0
        self.messages_received = 0
        self.blocks_synced = 0
        
        # Running flag
        self.running = False
        
        # Bootstrap
        if bootstrap_peers:
            for addr in bootstrap_peers:
                self.add_peer(addr, 0)
    
    def _generate_node_id(self) -> str:
        """Generate unique node ID."""
        data = str(time.time()) + str(id(self))
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def add_peer(self, address: str, height: int = 0):
        """Add a peer to the list."""
        if address not in self.peers and len(self.peers) < self.max_peers:
            self.peers[address] = Peer(
                address=address,
                last_seen=time.time(),
                height=height,
                capabilities=['sync', 'relay'],
            )
    
    def remove_peer(self, address: str):
        """Remove a peer."""
        if address in self.peers:
            del self.peers[address]
    
    def register_handler(self, msg_type: str, handler: Callable):
        """Register message handler."""
        self.handlers[msg_type] = handler
    
    async def start(self):
        """Start the node (discovery + sync)."""
        self.running = True
        
        # Start UDP discovery
        asyncio.create_task(self._discovery_listener())
        asyncio.create_task(self._discovery_broadcaster())
        
        # Start TCP sync server
        server = await asyncio.start_server(
            self._handle_connection,
            self.listen_addr,
            self.port
        )
        
        print(f"Node {self.node_id} listening on {self.listen_addr}:{self.port}")
        print(f"Peers: {len(self.peers)}")
        
        async with server:
            await server.serve_forever()
    
    async def _discovery_listener(self):
        """Listen for UDP discovery messages."""
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: DiscoveryProtocol(self),
            local_addr=(self.listen_addr, self.DISCOVERY_PORT)
        )
        
        while self.running:
            await asyncio.sleep(1)
    
    async def _discovery_broadcaster(self):
        """Broadcast presence periodically."""
        while self.running:
            await self._broadcast_presence()
            await asyncio.sleep(30)  # Every 30 seconds
    
    async def _broadcast_presence(self):
        """Broadcast node presence to network."""
        message = {
            'type': 'discovery',
            'node_id': self.node_id,
            'address': f"{self.listen_addr}:{self.port}",
            'timestamp': time.time(),
            'version': self.PROTOCOL_VERSION,
        }
        
        # Broadcast to local network (simplified)
        # In production: use DHT or bootstrap nodes
        try:
            transport = asyncio.get_event_loop()._transport
            # Would send to 255.255.255.255 here
        except:
            pass
    
    async def _handle_connection(self, reader, writer):
        """Handle incoming TCP connection."""
        addr = writer.get_extra_info('peername')
        
        try:
            # Read message length (4 bytes)
            length_data = await reader.read(4)
            if not length_data:
                return
            
            msg_len = int.from_bytes(length_data, 'big')
            
            # Read full message
            data = await reader.read(msg_len)
            message = json.loads(data.decode('utf-8'))
            
            self.messages_received += 1
            
            # Handle message
            response = await self._process_message(message, addr)
            
            if response:
                await self._send_response(writer, response)
                
        except Exception as e:
            print(f"Error handling connection from {addr}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def _process_message(self, message: Dict, addr) -> Optional[Dict]:
        """Process incoming message."""
        msg_type = message.get('type')
        
        if msg_type in self.handlers:
            return await self.handlers[msg_type](message, addr)
        
        return None
    
    async def _send_response(self, writer, response: Dict):
        """Send response back."""
        data = json.dumps(response).encode('utf-8')
        length = len(data).to_bytes(4, 'big')
        
        writer.write(length + data)
        await writer.drain()
        self.messages_sent += 1
    
    async def send_to_peer(self, peer_addr: str, message: Dict) -> Optional[Dict]:
        """Send message to specific peer."""
        try:
            host, port = peer_addr.rsplit(':', 1)
            port = int(port)
            
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=5.0
            )
            
            # Send
            data = json.dumps(message).encode('utf-8')
            length = len(data).to_bytes(4, 'big')
            writer.write(length + data)
            await writer.drain()
            self.messages_sent += 1
            
            # Read response
            length_data = await asyncio.wait_for(
                reader.read(4),
                timeout=5.0
            )
            
            if length_data:
                msg_len = int.from_bytes(length_data, 'big')
                data = await asyncio.wait_for(
                    reader.read(msg_len),
                    timeout=5.0
                )
                
                self.messages_received += 1
                return json.loads(data.decode('utf-8'))
                
        except Exception as e:
            print(f"Error sending to {peer_addr}: {e}")
            self.remove_peer(peer_addr)
        
        return None
    
    async def broadcast(self, message: Dict):
        """Broadcast message to all peers."""
        for peer_addr in list(self.peers.keys()):
            await self.send_to_peer(peer_addr, message)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get node statistics."""
        return {
            'node_id': self.node_id,
            'peers': len(self.peers),
            'messages_sent': self.messages_sent,
            'messages_received': self.messages_received,
            'blocks_synced': self.blocks_synced,
        }


class DiscoveryProtocol(asyncio.DatagramProtocol):
    """UDP discovery protocol handler."""
    
    def __init__(self, node: MicroNode):
        self.node = node
    
    def datagram_received(self, data, addr):
        """Handle UDP datagram."""
        try:
            message = json.loads(data.decode('utf-8'))
            
            if message.get('type') == 'discovery':
                peer_addr = message.get('address')
                if peer_addr and peer_addr != f"{self.node.listen_addr}:{self.node.port}":
                    self.node.add_peer(peer_addr, message.get('height', 0))
                    
        except Exception as e:
            pass


# Built-in handlers for blockchain sync
async def handle_get_blocks(message: Dict, addr, ledger) -> Dict:
    """Handle block request."""
    from_height = message.get('from_height', 0)
    limit = message.get('limit', 10)
    
    blocks = []
    for i in range(from_height, min(from_height + limit, ledger.height + 1)):
        block = ledger.get_block(i)
        if block:
            blocks.append(block.to_dict())
    
    return {
        'type': 'blocks_response',
        'blocks': blocks,
        'height': ledger.height,
    }


async def handle_get_tx(message: Dict, addr, mempool) -> Dict:
    """Handle transaction request."""
    return {
        'type': 'tx_response',
        'transactions': mempool,
    }


if __name__ == "__main__":
    print("MicroNode Test")
    print("=" * 40)
    
    node = MicroNode()
    
    # Register handlers
    async def ping_handler(msg, addr):
        return {'type': 'pong', 'time': time.time()}
    
    node.register_handler('ping', ping_handler)
    
    print(f"Node ID: {node.node_id}")
    print(f"Listen: {node.listen_addr}:{node.port}")
    
    # Would run with: asyncio.run(node.start())
    # For demo, just show stats
    print(f"\nStats: {node.get_stats()}")
    print("\nNode ready (run with asyncio.run(node.start()))")
