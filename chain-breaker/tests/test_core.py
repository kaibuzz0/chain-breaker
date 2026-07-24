"""
Unit Tests for Chain-Breaker Core
==================================

Tests Block, Blockchain, and Consensus modules.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
import time
import tempfile
import shutil

# Import modules directly
import importlib.util

crypto_dir = os.path.join(os.path.dirname(__file__), '..', 'chain-breaker', 'crypto')
core_dir = os.path.join(os.path.dirname(__file__), '..', 'chain-breaker', 'core')
consensus_dir = os.path.join(os.path.dirname(__file__), '..', 'chain-breaker', 'consensus')

# Load modules
spec = importlib.util.spec_from_file_location("e8_core", os.path.join(crypto_dir, "e8_core.py"))
e8_core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e8_core)

spec = importlib.util.spec_from_file_location("e8_hash", os.path.join(crypto_dir, "e8_hash.py"))
e8_hash = importlib.util.module_from_spec(spec2 := spec)
spec2.loader.exec_module(e8_hash)

spec = importlib.util.spec_from_file_location("block", os.path.join(core_dir, "block.py"))
block_mod = importlib.util.module_from_spec(spec3 := spec)
spec3.loader.exec_module(block_mod)
Block = block_mod.Block

spec = importlib.util.spec_from_file_location("blockchain", os.path.join(core_dir, "blockchain.py"))
bc_mod = importlib.util.module_from_spec(spec4 := spec)
spec4.loader.exec_module(bc_mod)
Blockchain = bc_mod.Blockchain


class TestBlock(unittest.TestCase):
    """Test Block class."""
    
    def test_block_creation(self):
        """Test creating a block."""
        block = Block(
            index=0,
            timestamp=time.time(),
            data="Genesis",
            previous_hash="0" * 64,
            difficulty=100
        )
        self.assertEqual(block.index, 0)
        self.assertEqual(block.data, "Genesis")
    
    def test_block_hash(self):
        """Test block hash computation."""
        block = Block(
            index=1,
            timestamp=time.time(),
            data="Test",
            previous_hash="a" * 64,
            difficulty=100
        )
        block.compute_hash()
        self.assertEqual(len(block.hash), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in block.hash))
    
    def test_block_validation(self):
        """Test block validation."""
        block = Block(
            index=0,
            timestamp=time.time(),
            data="Genesis",
            previous_hash="0" * 64,
            difficulty=100
        )
        block.compute_hash()
        self.assertTrue(block.validate())


class TestBlockchain(unittest.TestCase):
    """Test Blockchain class."""
    
    def setUp(self):
        """Set up test blockchain."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.blockchain = Blockchain(db_path=self.db_path)
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)
    
    def test_genesis_block(self):
        """Test genesis block creation."""
        genesis = self.blockchain.create_genesis_block()
        self.assertEqual(genesis.index, 0)
        self.assertEqual(genesis.previous_hash, "0" * 64)
        self.assertTrue(genesis.validate())
    
    def test_add_block(self):
        """Test adding blocks."""
        genesis = self.blockchain.create_genesis_block()
        self.blockchain.chain.append(genesis)
        
        block = self.blockchain.add_block("Test Block", mine=False)
        self.assertEqual(block.index, 1)
        self.assertEqual(len(self.blockchain.chain), 2)
    
    def test_chain_validation(self):
        """Test chain validation."""
        genesis = self.blockchain.create_genesis_block()
        self.blockchain.chain.append(genesis)
        self.blockchain.add_block("Block 1", mine=False)
        self.blockchain.add_block("Block 2", mine=False)
        
        self.assertTrue(self.blockchain.validate_chain())
    
    def test_get_block(self):
        """Test block retrieval."""
        genesis = self.blockchain.create_genesis_block()
        self.blockchain.chain.append(genesis)
        
        retrieved = self.blockchain.get_block_by_index(0)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.data, genesis.data)


class TestE8Integration(unittest.TestCase):
    """Test E8 cryptography integration."""
    
    def test_e8_lattice(self):
        """Test E8 lattice generation."""
        e8 = e8_core.get_e8_lattice()
        self.assertEqual(len(e8.roots), 240)
        
        # Check root norms
        for root in e8.roots:
            norm = sum(x*x for x in root)
            self.assertAlmostEqual(norm, 2.0, places=5)
    
    def test_weyl_reflection(self):
        """Test Weyl reflection is self-inverse."""
        e8 = e8_core.get_e8_lattice()
        v = [1.0, 0.5, 0.3, 0.2, 0.1, 0.0, 0.0, 0.0]
        
        reflected = e8.weyl_reflection(v, 0)
        reflected2 = e8.weyl_reflection(reflected, 0)
        
        for a, b in zip(v, reflected2):
            self.assertAlmostEqual(a, b, places=10)


if __name__ == "__main__":
    print("Running Chain-Breaker Tests...")
    unittest.main(verbosity=2)
