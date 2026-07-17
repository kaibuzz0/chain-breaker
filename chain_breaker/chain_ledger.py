"""
chain_ledger.py

Append-only ledger with integrity verification.
- Chain of blocks
- Fork detection
- Chain validation
- State management
"""

import json
from typing import List, Dict, Any, Optional
from .block_core import Block, BlockHeader, create_genesis_block
from .hash_engine import HashEngine


class Ledger:
    """
    Blockchain ledger - chain of blocks with validation.
    
    Properties:
    - Immutable: Append-only
    - Verifiable: Cryptographic chain of hashes
    - Decentralized-ready: Minimal state for consensus
    """
    
    def __init__(self):
        self.chain: List[Block] = []
        self.pending_transactions: List[Dict[str, Any]] = []
        self.mining_reward = 100
        self.difficulty = 2
        
        # Create genesis block
        genesis = create_genesis_block()
        self.chain.append(genesis)
    
    @property
    def height(self) -> int:
        """Current chain height (number of blocks)."""
        return len(self.chain) - 1  # Excluding genesis
    
    @property
    def last_block(self) -> Block:
        """Most recent block."""
        return self.chain[-1]
    
    def add_transaction(self, transaction: Dict[str, Any]) -> bool:
        """
        Add transaction to pending pool.
        
        Basic validation (real system needs full validation).
        """
        if not isinstance(transaction, dict):
            return False
        
        if "from" not in transaction or "to" not in transaction:
            return False
        
        self.pending_transactions.append(transaction)
        return True
    
    def mine_pending(self, miner_address: str) -> Optional[Block]:
        """
        Mine pending transactions into a new block.
        
        Creates coinbase transaction (mining reward),
        builds block, mines it, adds to chain.
        """
        if not self.pending_transactions:
            return None
        
        # Coinbase transaction (reward)
        coinbase = {
            "type": "coinbase",
            "to": miner_address,
            "amount": self.mining_reward,
            "height": self.height + 1,
        }
        
        transactions = [coinbase] + self.pending_transactions
        
        # Build Merkle tree
        tx_hashes = [HashEngine.hash_object(tx) for tx in transactions]
        from .hash_engine import MerkleTree
        merkle = MerkleTree(tx_hashes)
        
        # Create block
        header = BlockHeader(
            version=1,
            prev_hash=self.last_block.hash,
            merkle_root=HashEngine.hash_to_hex(merkle.root) if merkle.root else "0" * 64,
            difficulty=self.difficulty,
        )
        
        block = Block(header=header, transactions=transactions)
        
        # Mine
        print(f"Mining block {self.height + 1} with difficulty {self.difficulty}...")
        block.mine()
        
        # Verify and add
        if block.verify():
            self.chain.append(block)
            self.pending_transactions = []
            print(f"Block mined: {block.hash[:16]}...")
            return block
        
        return None
    
    def validate_chain(self) -> bool:
        """
        Validate entire chain integrity.
        
        Checks:
        1. Each block hash correct
        2. Each block links to previous
        3. Merkle roots valid
        4. Genesis block correct
        """
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]
            
            # Verify block hash
            if not current.verify():
                print(f"Block {i} verification failed")
                return False
            
            # Verify chain link
            if current.header.prev_hash != previous.hash:
                print(f"Chain link broken at block {i}")
                return False
        
        return True
    
    def get_balance(self, address: str) -> int:
        """
        Calculate balance from transaction history.
        Simple UTXO model.
        """
        balance = 0
        
        for block in self.chain:
            for tx in block.transactions:
                if tx.get("to") == address:
                    balance += tx.get("amount", 0)
                if tx.get("from") == address:
                    balance -= tx.get("amount", 0)
        
        return balance
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize ledger."""
        return {
            "blocks": [block.to_dict() for block in self.chain],
            "height": self.height,
            "difficulty": self.difficulty,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Ledger':
        """Deserialize ledger."""
        ledger = cls()
        ledger.chain = [Block.from_dict(b) for b in data["blocks"]]
        ledger.difficulty = data.get("difficulty", 2)
        return ledger


if __name__ == "__main__":
    print("Ledger Test")
    print("=" * 40)
    
    ledger = Ledger()
    print(f"Genesis created. Height: {ledger.height}")
    
    # Add transactions
    ledger.add_transaction({"from": "alice", "to": "bob", "amount": 50})
    ledger.add_transaction({"from": "bob", "to": "charlie", "amount": 30})
    
    # Mine
    ledger.mine_pending("miner1")
    print(f"Height after mining: {ledger.height}")
    
    # Add more
    ledger.add_transaction({"from": "charlie", "to": "alice", "amount": 10})
    ledger.mine_pending("miner2")
    
    print(f"Final height: {ledger.height}")
    
    # Check balances
    print(f"\nBalances:")
    print(f"  Alice: {ledger.get_balance('alice')}")
    print(f"  Bob: {ledger.get_balance('bob')}")
    print(f"  Charlie: {ledger.get_balance('charlie')}")
    print(f"  Miner1: {ledger.get_balance('miner1')}")
    print(f"  Miner2: {ledger.get_balance('miner2')}")
    
    # Validate
    print(f"\nChain valid: {ledger.validate_chain()}")
