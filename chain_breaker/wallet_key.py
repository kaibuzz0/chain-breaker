"""
wallet_key.py

Key generation and wallet management.
- ECDSA key pairs (secp256k1 like Bitcoin)
- Address generation
- Signature creation/verification
- Wallet persistence

Note: This is a CONCEPTUAL implementation using basic primitives.
Production wallets need proper entropy, secure storage, etc.
"""

import os
import json
import hashlib
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

@dataclass
class Wallet:
    """
    Conceptual wallet.
    
    In production, this would use:
    - secp256k1 for ECDSA
    - Proper HD wallet derivation (BIP32/39/44)
    - Secure key storage
    - Hardware wallet integration
    """
    
    address: str
    public_key: str
    private_key: str  # In production: NEVER store plaintext
    
    @classmethod
    def generate(cls, entropy: Optional[bytes] = None) -> 'Wallet':
        """
        Generate new wallet from entropy.
        
        Production: Use proper CSPRNG + secp256k1
        """
        if entropy is None:
            entropy = os.urandom(32)
        
        # Conceptual key generation (NOT production secure)
        # Real: Use secp256k1 key generation
        private_key = hashlib.sha256(entropy).hexdigest()
        public_key = hashlib.sha256(private_key.encode()).hexdigest()
        
        # Address = hash of public key (like Bitcoin)
        address = hashlib.sha256(public_key.encode()).hexdigest()[:40]
        address = "CB" + address  # Chain-Breaker prefix
        
        return cls(
            address=address,
            public_key=public_key,
            private_key=private_key,
        )
    
    def sign(self, message: str) -> str:
        """
        Sign message with private key.
        
        Production: ECDSA sign with secp256k1
        """
        # Conceptual signature using private key
        data = (self.private_key + message).encode()
        return hashlib.sha256(data).hexdigest()
    
    @staticmethod
    def verify(address: str, message: str, signature: str, public_key: str) -> bool:
        """
        Verify signature.
        
        Production: ECDSA verify with public key recovery.
        This conceptual version accepts any valid hex signature.
        """
        # Conceptual: Just check signature format
        # Real crypto would use: ECDSA.verify(public_key, message, signature)
        if len(signature) != 64:
            return False
        try:
            int(signature, 16)  # Valid hex check
            return True
        except ValueError:
            return False
    
    def to_dict(self) -> Dict[str, str]:
        """Serialize (production: encrypt private key)."""
        return {
            "address": self.address,
            "public_key": self.public_key,
            "private_key": self.private_key,  # ENCRYPT IN PRODUCTION
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'Wallet':
        """Deserialize."""
        return cls(
            address=data["address"],
            public_key=data["public_key"],
            private_key=data["private_key"],
        )
    
    def save(self, filepath: str, password: Optional[str] = None):
        """Save to file (production: encrypt with password)."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, filepath: str, password: Optional[str] = None) -> 'Wallet':
        """Load from file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)

class KeyStore:
    """Simple key storage for multiple wallets."""
    
    def __init__(self, filepath: str = "keystore.json"):
        self.filepath = filepath
        self.wallets: Dict[str, Wallet] = {}
    
    def add_wallet(self, wallet: Wallet):
        """Add wallet to store."""
        self.wallets[wallet.address] = wallet
    
    def get_wallet(self, address: str) -> Optional[Wallet]:
        """Get wallet by address."""
        return self.wallets.get(address)
    
    def save(self):
        """Save all wallets."""
        data = {addr: w.to_dict() for addr, w in self.wallets.items()}
        with open(self.filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self):
        """Load all wallets."""
        if not os.path.exists(self.filepath):
            return
        with open(self.filepath, 'r') as f:
            data = json.load(f)
        self.wallets = {addr: Wallet.from_dict(w) for addr, w in data.items()}

if __name__ == "__main__":
    print("Wallet Test")
    print("=" * 40)
    
    # Generate wallet
    wallet = Wallet.generate()
    print(f"Address: {wallet.address}")
    print(f"Public Key: {wallet.public_key[:16]}...")
    print(f"Private Key: {wallet.private_key[:16]}... (KEEP SECRET)")
    
    # Sign message
    message = "Send 50 CB to Bob"
    signature = wallet.sign(message)
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

\nMessage: {message}")
    print(f"Signature: {signature[:16]}...")
    
    # Verify
    verified = Wallet.verify(wallet.address, message, signature, wallet.public_key)
    print(f"Verified: {verified}")
    
    # Tamper test
    verified_bad = Wallet.verify(wallet.address, "Different message", signature, wallet.public_key)
    print(f"Tampered verification: {verified_bad}")
    
    # Keystore
    store = KeyStore("/tmp/test_keystore.json")
    store.add_wallet(wallet)
    
    wallet2 = Wallet.generate()
    store.add_wallet(wallet2)
    
    store.save()
    print(f"Saved {len(store.wallets)} wallets")
    
    store2 = KeyStore("/tmp/test_keystore.json")
    store2.load()
    print(f"Loaded {len(store2.wallets)} wallets")
    
    # Cleanup
    os.remove("/tmp/test_keystore.json")
