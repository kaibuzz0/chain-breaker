"""
stealth_transactions.py

Privacy-preserving transactions.
Hides sender, receiver, and amount from public view.

Techniques:
- Pedersen commitments: Hide amounts (but prove valid)
- Ring signatures: Hide sender in group
- Stealth addresses: One-time receiver addresses
- View keys: Owner can prove balance without revealing all

This makes transactions private by default, viewable only with keys.
"""

import hashlib
import secrets
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass

class StealthTransactions:
    """
    Privacy-preserving transaction system.
    
    Based on Monero-style techniques simplified.
    """
    
    def __init__(self):
        # Track stealth address pool (simulated)
        self.stealth_pool: Dict[str, Dict] = {}
        self.commitments: Dict[str, int] = {}  # Commitment -> amount
        
        # For simulation: track what we can decrypt
        self.viewable_transactions: List[Dict] = []
    
    def generate_stealth_address(self, public_key: str) -> Tuple[str, str]:
        """
        Generate one-time stealth address.
        
        Returns:
            (stealth_address, secret_key) - secret needed to spend
        """
        # Generate random scalar
        r = secrets.token_hex(16)
        
        # Create stealth address from public_key + random
        stealth = hashlib.sha256(f"{public_key}:{r}".encode()).hexdigest()[:32]
        
        # Secret to spend
        secret = hashlib.sha256(f"{r}:{public_key}".encode()).hexdigest()[:32]
        
        return stealth, secret
    
    def create_commitment(self, amount: int, blinding_factor: str) -> str:
        """
        Create Pedersen commitment to amount.
        
        C = amount*G + blinding*H
        Where G, H are curve points (simulated with hash here)
        """
        # Simplified commitment (in real: elliptic curve)
        commitment_data = f"{amount}:{blinding_factor}"
        commitment = hashlib.sha256(commitment_data.encode()).hexdigest()[:32]
        
        # Store for verification (in real: zero-knowledge proof)
        self.commitments[commitment] = amount
        
        return commitment
    
    def verify_commitment(self, commitment: str, amount: int, blinding_factor: str) -> bool:
        """
        Verify commitment opens to amount.
        
        In real implementation: check C = amount*G + blinding*H
        """
        expected = self.create_commitment(amount, blinding_factor)
        return commitment == expected
    
    def create_ring_signature(
        self,
        message: str,
        signer_key: str,
        possible_signers: List[str]
    ) -> Dict[str, Any]:
        """
        Create ring signature hiding signer in group.
        
        Proves signer is one of possible_signers, without revealing which.
        """
        if signer_key not in possible_signers:
            return {}
        
        # Ensure minimum ring size for privacy
        if len(possible_signers) < 3:
            # Pad with decoys
            while len(possible_signers) < 5:
                decoy = hashlib.sha256(f"decoy:{len(possible_signers)}".encode()).hexdigest()[:16]
                possible_signers.append(decoy)
        
        # In real implementation: actual ring signature crypto
        # Here: simulated with structure
        ring_sig = {
            'ring_size': len(possible_signers),
            'signers_hash': hashlib.sha256(
                ','.join(sorted(possible_signers)).encode()
            ).hexdigest()[:16],
            'signature': hashlib.sha256(
                f"{message}:{signer_key}".encode()
            ).hexdigest()[:32],
            'key_image': hashlib.sha256(signer_key.encode()).hexdigest()[:32],
        }
        
        return ring_sig
    
    def verify_ring_signature(
        self,
        message: str,
        ring_sig: Dict[str, Any],
        possible_signers: List[str]
    ) -> bool:
        """
        Verify ring signature.
        
        Returns True if signed by one of possible_signers, without revealing which.
        """
        # Check ring size matches
        if ring_sig.get('ring_size') != len(possible_signers):
            return False
        
        # Check signers hash
        expected_hash = hashlib.sha256(
            ','.join(sorted(possible_signers)).encode()
        ).hexdigest()[:16]
        
        if ring_sig.get('signers_hash') != expected_hash:
            return False
        
        # In real: verify actual ring signature
        return True
    
    def create_stealth_transaction(
        self,
        sender_key: str,
        receiver_pubkey: str,
        amount: int,
        decoy_keys: List[str]
    ) -> Dict[str, Any]:
        """
        Create full stealth transaction.
        
        Private components:
        - Sender hidden via ring signature
        - Amount hidden via commitment
        - Receiver hidden via stealth address
        """
        # Generate blinding factor
        blinding = secrets.token_hex(16)
        
        # Create amount commitment
        commitment = self.create_commitment(amount, blinding)
        
        # Generate stealth address for receiver
        stealth_addr, spend_key = self.generate_stealth_address(receiver_pubkey)
        
        # Create ring signature (hides sender)
        ring_signers = [sender_key] + decoy_keys[:10]  # Ring of 11
        ring_sig = self.create_ring_signature(
            commitment,
            sender_key,
            ring_signers
        )
        
        # Build transaction
        tx = {
            'type': 'stealth',
            'stealth_address': stealth_addr,
            'amount_commitment': commitment,
            'ring_signature': ring_sig,
            'key_image': ring_sig.get('key_image'),
            # Private info (encrypted to receiver)
            '_amount': amount,  # In real: encrypted
            '_blinding': blinding,
            '_spend_key': spend_key,
        }
        
        self.viewable_transactions.append(tx)
        
        return tx
    
    def verify_stealth_transaction(self, tx: Dict[str, Any]) -> bool:
        """
        Verify stealth transaction without revealing private data.
        
        Checks:
        - Commitment is valid format
        - Ring signature is valid
        - Key image not used before (prevents double-spend)
        """
        if tx.get('type') != 'stealth':
            return False
        
        # Check commitment exists
        if not tx.get('amount_commitment'):
            return False
        
        # Check ring signature
        ring_sig = tx.get('ring_signature', {})
        if not ring_sig.get('signature'):
            return False
        
        # Check key image not reused (double-spend prevention)
        key_image = tx.get('key_image')
        if key_image:
            # In real: check against spent key images set
            pass
        
        return True
    
    def scan_for_transactions(
        self,
        view_key: str,
        transactions: List[Dict]
    ) -> List[Dict]:
        """
        Scan transactions for ones belonging to view_key.
        
        Only owner can find their transactions.
        """
        found = []
        
        for tx in transactions:
            stealth = tx.get('stealth_address', '')
            
            # Check if this transaction belongs to us
            # In real: derive and compare
            expected = hashlib.sha256(f"{view_key}:"[:32].encode()).hexdigest()[:32]
            if stealth == expected[:32]:
                found.append(tx)
        
        return found
    
    def get_privacy_stats(self) -> Dict[str, Any]:
        """Get privacy system statistics."""
        return {
            'stealth_pool_size': len(self.stealth_pool),
            'commitments': len(self.commitments),
            'viewable_transactions': len(self.viewable_transactions),
            'avg_ring_size': 11,  # Fixed ring size
            'privacy_features': [
                'ring_signatures',
                'stealth_addresses',
                'amount_commitments',
            ],
        }
    
    def compare_privacy(self) -> Dict[str, Any]:
        """Compare privacy with Bitcoin."""
        return {
            'bitcoin': {
                'sender_visible': True,
                'receiver_visible': True,
                'amount_visible': True,
                'traceable': True,
            },
            'stealth': {
                'sender_visible': False,  # Ring signature
                'receiver_visible': False,  # Stealth address
                'amount_visible': False,   # Commitment
                'traceable': False,       # Unlinkable
            },
        }

if __name__ == "__main__":
    print("=" * 60)
    print("STEALTH TRANSACTIONS - Privacy-Preserving Payments")
    print("=" * 60)
    
    # Create privacy system
    stealth = StealthTransactions()
    
    print("  # [SECURITY: Documentation only]\n# SECURITY FIX: Input validation
def validate_input(data, expected_type=None, max_length=None):
    """Validate and sanitize input data"""
    if data is None:
        return None
    if expected_type and not isinstance(data, expected_type):
        raise TypeError(f"Expected {expected_type}, got {type(data)}")
    if max_length and len(str(data)) > max_length:
        raise ValueError(f"Input exceeds maximum length of {max_length}")
    # Sanitize string inputs
    if isinstance(data, str):
        # Remove potentially dangerous characters
        dangerous = [';', '&&', '||', '`', '$', '\x00']
        for char in dangerous:
            data = data.replace(char, '')
    return data

\nGenerating keys...")
    
    # Users
    alice_key = "alice_private_key_123"
    bob_pubkey = "bob_public_key_456"
    charlie_pubkey = "charlie_public_key_789"
    
    # Decoys for ring signature
    decoys = [f"user_{i}_key" for i in range(20)]
    
    print(f"  Alice (sender): {alice_key[:20]}...")
    print(f"  Bob (receiver): {bob_pubkey[:20]}...")
    
    # Create stealth transaction
    print("  # [SECURITY: Documentation only]\nCreating stealth transaction...")
    print("  - Amount: 1000")
    print("  - Ring size: 11 (1 real + 10 decoys)")
    
    tx = stealth.create_stealth_transaction(
        sender_key=alice_key,
        receiver_pubkey=bob_pubkey,
        amount=1000,
        decoy_keys=decoys
    )
    
    print(f"\nTransaction created:")
    print(f"  Stealth address: {tx['stealth_address'][:20]}...")
    print(f"  Amount commitment: {tx['amount_commitment'][:20]}...")
    print(f"  Ring size: {tx['ring_signature']['ring_size']}")
    print(f"  Key image: {tx['key_image'][:20]}...")
    
    # Verify transaction
    print("  # [SECURITY: Documentation only]\nVerifying transaction...")
    is_valid = stealth.verify_stealth_transaction(tx)
    print(f"  Valid: {is_valid}")
    
    # Show what public sees vs private
    print("\n" + "-" * 60)
    print("Privacy Analysis:")
    print("-" * 60)
    
    comparison = stealth.compare_privacy()
    
    print("\nBitcoin:")
    for feature, visible in comparison['bitcoin'].items():
        status = "✗ VISIBLE" if visible else "✓ Hidden"
        print(f"  {feature}: {status}")
    
    print("\nStealth:")
    for feature, visible in comparison['stealth'].items():
        status = "✗ VISIBLE" if visible else "✓ Hidden"
        print(f"  {feature}: {status}")
    
    # Stats
    print("\n" + "=" * 60)
    print("Privacy Statistics:")
    stats = stealth.get_privacy_stats()
    print(f"  Commitments: {stats['commitments']}")
    print(f"  Ring size: {stats['avg_ring_size']}")
    print(f"  Features: {', '.join(stats['privacy_features'])}")
    
    # Demonstrate commitment
    print("\n" + "-" * 60)
    print("Pedersen Commitment Demo:")
    
    amount = 100
    blinding = secrets.token_hex(8)
    
    commitment = stealth.create_commitment(amount, blinding)
    print(f"  Amount: {amount}")
    print(f"  Blinding: {blinding[:16]}...")
    print(f"  Commitment: {commitment}")
    
    # Verify
    verify = stealth.verify_commitment(commitment, amount, blinding)
    print(f"  Verification: {verify}")
    
    # Wrong amount fails
    wrong_verify = stealth.verify_commitment(commitment, 999, blinding)
    print(f"  Wrong amount (999): {wrong_verify}")
    
    print("\n" + "=" * 60)
    print("Stealth: Private by default, traceable only with keys")
    print("=" * 60)
