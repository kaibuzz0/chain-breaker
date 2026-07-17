#!/usr/bin/env python3
"""
Chain-Breaker Demo

Demonstrates all microparts working together:
1. Create wallet
2. Create ledger (genesis block)
3. Add transactions
4. Mine blocks
5. Verify chain
6. Check balances
"""

import sys
sys.path.insert(0, '/root/chain-breaker')

from chain_breaker import Wallet, Ledger


def main():
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║           CHAIN-BREAKER: Blockchain Microparts            ║")
    print("║              Conceptual Implementation v0.1.0           ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    
    # Create wallets
    print("\n[1] Creating wallets...")
    alice = Wallet.generate()
    bob = Wallet.generate()
    miner = Wallet.generate()
    
    print(f"  Alice:   {alice.address[:20]}...")
    print(f"  Bob:     {bob.address[:20]}...")
    print(f"  Miner:   {miner.address[:20]}...")
    
    # Create ledger
    print("\n[2] Initializing ledger...")
    ledger = Ledger()
    print(f"  Genesis block created")
    print(f"  Initial height: {ledger.height}")
    
    # Add transactions
    print("\n[3] Adding transactions...")
    ledger.add_transaction({"from": "genesis", "to": alice.address, "amount": 1000})
    ledger.add_transaction({"from": alice.address, "to": bob.address, "amount": 50})
    ledger.add_transaction({"from": alice.address, "to": bob.address, "amount": 25})
    
    print(f"  {len(ledger.pending_transactions)} transactions pending")
    
    # Mine
    print("\n[4] Mining block...")
    ledger.mine_pending(miner.address)
    print(f"  Height: {ledger.height}")
    print(f"  Last block: {ledger.last_block.hash[:20]}...")
    
    # Add more
    print("\n[5] Adding more transactions...")
    ledger.add_transaction({"from": bob.address, "to": alice.address, "amount": 10})
    ledger.add_transaction({"from": bob.address, "to": miner.address, "amount": 5})
    
    print("\n[6] Mining next block...")
    ledger.mine_pending(miner.address)
    print(f"  Height: {ledger.height}")
    
    # Verify
    print("\n[7] Verifying chain...")
    is_valid = ledger.validate_chain()
    print(f"  Chain valid: {is_valid}")
    
    # Balances
    print("\n[8] Final balances:")
    print(f"  Alice:   {ledger.get_balance(alice.address)}")
    print(f"  Bob:     {ledger.get_balance(bob.address)}")
    print(f"  Miner:   {ledger.get_balance(miner.address)}")
    
    print("\n" + "="*59)
    print("Demo complete. Chain-Breaker microparts functional.")
    print("="*59)


if __name__ == "__main__":
    main()
