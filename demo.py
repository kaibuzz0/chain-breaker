#!/usr/bin/env python3
"""
Chain-Breaker Integration Demo

Demonstrates complete blockchain workflow:
1. Initialize blockchain with genesis
2. Start mesh node
3. Mine blocks
4. Broadcast to peers
5. Sync chains

Run two instances to test P2P:
    python demo.py --port 8333
    python demo.py --port 8334 --connect 127.0.0.1:8333
"""

import argparse
import time
import threading
from chain_core import Blockchain, Block, ScriptureTransaction
from mesh_node import MeshNode
from mobile_db import MobileChainDB
import hashlib

def main():
    parser = argparse.ArgumentParser(description='Chain-Breaker Demo Node')
    parser.add_argument('--port', type=int, default=8333, help='UDP port')
    parser.add_argument('--connect', type=str, help='Connect to peer (host:port)')
    parser.add_argument('--db', type=str, default='chain.db', help='Database file')
    parser.add_argument('--mine', action='store_true', help='Mine blocks')
    args = parser.parse_args()
    
    print("=" * 70)
    print("⛓️  CHAIN-BREAKER DEMO NODE")
    print("=" * 70)
    print(f"Port: {args.port}")
    print(f"Database: {args.db}")
    print()
    
    # 1. Initialize blockchain
    print("1️⃣ Initializing blockchain...")
    blockchain = Blockchain()
    print(f"   Genesis block: {blockchain.chain[0].hash()[:20]}...")
    print(f"   Chain height: {len(blockchain.chain)}")
    print()
    
    # 2. Initialize database
    print("2️⃣ Initializing database...")
    db = MobileChainDB(args.db, mode="light")
    db.store_block(blockchain.chain[0])
    print(f"   Database: {args.db}")
    print()
    
    # 3. Start mesh node
    print("3️⃣ Starting mesh node...")
    node = MeshNode(blockchain, port=args.port)
    node.start()
    print(f"   Node ID: {node._get_node_id()[:20]}...")
    print(f"   Port: {args.port}")
    print()
    
    # 4. Connect to peer if specified
    if args.connect:
        print("4️⃣ Connecting to peer...")
        host, port = args.connect.split(':')
        node.connect_to_peer(host, int(port))
        time.sleep(1)
        print(f"   Connected peers: {len(node.peers)}")
        print()
    
    # 5. Set up callbacks
    def on_block_received(block_data, peer):
        print(f"\n📥 Received block from {peer.address}")
        # In production, validate and add to chain
    
    node.on_block_received = on_block_received
    
    # 6. Mine blocks (if requested)
    if args.mine:
        print("5️⃣ Mining blocks...")
        print("   Press Ctrl+C to stop")
        print()
        
        try:
            block_count = 0
            while True:
                # Create new block
                new_block = Block(
                    prev_hash=blockchain.chain[-1].hash(),
                    transactions=[],
                    difficulty=blockchain.get_next_difficulty()
                )
                
                # Mine it
                print(f"⛏️  Mining block {len(blockchain.chain)}...", end=' ')
                if blockchain.mine_block(new_block, max_iterations=100000):
                    if blockchain.add_block(new_block):
                        db.store_block(new_block)
                        print(f"MINED! {new_block.hash()[:20]}...")
                        
                        # Broadcast to peers
                        node.broadcast_block(new_block)
                        block_count += 1
                        
                        # Stats
                        stats = node.get_stats()
                        print(f"   Chain height: {len(blockchain.chain)}")
                        print(f"   Peers: {stats['peers_connected']}")
                        print(f"   Messages sent: {stats['messages_sent']}")
                        print()
                        
                        time.sleep(5)  # Mine every 5 seconds for demo
                else:
                    print("FAILED (timeout)")
                    
        except KeyboardInterrupt:
            print(f"\n\n✅ Mined {block_count} blocks")
    
    else:
        # Just listen
        print("5️⃣ Listening for blocks...")
        print("   Press Ctrl+C to exit")
        print()
        
        try:
            while True:
                time.sleep(1)
                stats = node.get_stats()
                print(f"\r   Peers: {stats['peers_connected']} | "
                      f"Blocks: {len(blockchain.chain)} | "
                      f"Messages: {stats['messages_received']}", end='')
        except KeyboardInterrupt:
            print()
    
    # Cleanup
    print("\n🛑 Stopping node...")
    node.stop()
    
    # Final stats
    print("\n" + "=" * 70)
    print("📊 FINAL STATS")
    print("=" * 70)
    stats = node.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    print(f"   Database size: {db.get_db_size():,} bytes")
    print()
    print("✅ Demo complete")

if __name__ == "__main__":
    main()
