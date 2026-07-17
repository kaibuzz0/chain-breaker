"""
block_explorer.py

Simple block explorer for Chain-Breaker.
- View blocks by height
- View transactions
- Search by hash
- ASCII visualization
"""

import json
import os
from typing import Dict, Any, Optional, List


class BlockExplorer:
    """
    Minimal block explorer for pruned ledger.
    Works with full blocks, archived headers, or just hashes.
    """
    
    def __init__(self, ledger_path: str = 'ledger_state.json'):
        self.ledger_path = ledger_path
        self.ledger = None
        self.load_ledger()
    
    def load_ledger(self):
        """Load ledger from disk."""
        from chain_breaker.pruned_ledger import PrunedLedger
        
        self.ledger = PrunedLedger()
        
        if os.path.exists(self.ledger_path):
            with open(self.ledger_path, 'r') as f:
                data = json.load(f)
                # Restore what we can
                for addr, bal in data.get('balances', {}).items():
                    self.ledger.state[addr] = bal
    
    def get_block(self, height: int) -> Optional[Dict]:
        """Get block by height."""
        return self.ledger.get_block(height)
    
    def get_block_header(self, height: int) -> Optional[Dict]:
        """Get block header by height."""
        return self.ledger.get_block_header(height)
    
    def get_latest_blocks(self, count: int = 10) -> List[Dict]:
        """Get latest N blocks."""
        blocks = []
        for i in range(max(0, self.ledger.height - count), self.ledger.height + 1):
            block = self.get_block(i)
            if block:
                blocks.append({
                    'height': i,
                    'hash': block.hash[:16] + '...',
                    'tx_count': len(block.transactions),
                    'timestamp': block.header.timestamp,
                })
        return blocks
    
    def search(self, query: str) -> Dict[str, Any]:
        """Search for address, hash, or height."""
        results = {'type': 'unknown', 'data': None}
        
        # Try height
        try:
            height = int(query)
            block = self.get_block(height)
            if block:
                results['type'] = 'block'
                results['data'] = block.to_dict()
                return results
        except ValueError:
            pass
        
        # Try address
        if query.startswith('CB'):
            balance = self.ledger.get_balance(query)
            results['type'] = 'address'
            results['data'] = {
                'address': query,
                'balance': balance,
            }
            return results
        
        return results
    
    def display_block(self, block: Dict[str, Any]):
        """Display block details in ASCII."""
        print("╔" + "═" * 58 + "╗")
        print(f"║  BLOCK #{block.get('header', {}).get('nonce', '?')}".ljust(59) + "║")
        print("╠" + "═" * 58 + "╣")
        
        header = block.get('header', {})
        print(f"║  Hash:      {block.get('hash', '?'):56} ║")
        print(f"║  Prev Hash: {header.get('prev_hash', '?'):56} ║")
        print(f"║  Merkle:    {header.get('merkle_root', '?'):56} ║")
        print(f"║  Timestamp: {header.get('timestamp', '?'):56} ║")
        print(f"║  Difficulty: {header.get('difficulty', '?'):55} ║")
        print(f"║  Nonce:     {header.get('nonce', '?'):56} ║")
        print("╠" + "═" * 58 + "╣")
        
        txs = block.get('transactions', [])
        print(f"║  Transactions ({len(txs)}):".ljust(59) + "║")
        
        for i, tx in enumerate(txs[:5]):  # Show first 5
            from_addr = tx.get('from', '?')[:20]
            to_addr = tx.get('to', '?')[:20]
            amount = tx.get('amount', 0)
            print(f"║    {i+1}. {from_addr}... -> {to_addr}...: {amount}".ljust(58) + "║")
        
        if len(txs) > 5:
            print(f"║    ... and {len(txs) - 5} more".ljust(58) + "║")
        
        print("╚" + "═" * 58 + "╝")
    
    def display_chain_stats(self):
        """Display overall chain statistics."""
        stats = self.ledger.get_storage_stats()
        
        print("╔" + "═" * 58 + "╗")
        print("║" + " CHAIN STATISTICS ".center(58) + "║")
        print("╠" + "═" * 58 + "╣")
        print(f"║  Height:        {stats['height']:38} ║")
        print(f"║  Full Blocks:   {stats['full_blocks']:38} ║")
        print(f"║  Archived:      {stats['archived_blocks']:38} ║")
        print(f"║  Pruned:        {stats['pruned_blocks']:38} ║")
        print("╠" + "═" * 58 + "╣")
        print(f"║  Storage (MB):   {stats['total_estimated_mb']:38.4f} ║")
        print(f"║  Savings:       {stats['savings_vs_full']:38} ║")
        print("╚" + "═" * 58 + "╝")
        
        print("\nRecent Blocks:")
        print("-" * 60)
        print(f"{'Height':<10} {'Hash':<20} {'TXs':<6} {'Time':<20}")
        print("-" * 60)
        
        for block in self.get_latest_blocks(5):
            time_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(block['timestamp']))
            print(f"{block['height']:<10} {block['hash']:<20} {block['tx_count']:<6} {time_str}")


def main():
    """CLI interface for explorer."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Chain-Breaker Block Explorer')
    parser.add_argument('command', choices=['block', 'stats', 'search', 'recent'])
    parser.add_argument('arg', nargs='?', help='Block height, hash, or address')
    
    args = parser.parse_args()
    
    explorer = BlockExplorer()
    
    if args.command == 'stats':
        explorer.display_chain_stats()
    
    elif args.command == 'block':
        if not args.arg:
            print("Usage: block_explorer.py block <height>")
            return
        
        height = int(args.arg)
        block = explorer.get_block(height)
        if block:
            explorer.display_block(block.to_dict())
        else:
            header = explorer.get_block_header(height)
            if header:
                print(f"Block {height} (archived - header only):")
                print(json.dumps(header, indent=2))
            else:
                print(f"Block {height} not found")
    
    elif args.command == 'search':
        if not args.arg:
            print("Usage: block_explorer.py search <query>")
            return
        
        results = explorer.search(args.arg)
        print(f"Search results for '{args.arg}':")
        print(json.dumps(results, indent=2))
    
    elif args.command == 'recent':
        print("Recent Blocks:")
        print("-" * 60)
        for block in explorer.get_latest_blocks(10):
            print(f"  #{block['height']}: {block['hash']} ({block['tx_count']} txs)")


if __name__ == '__main__':
    import time
    main()
