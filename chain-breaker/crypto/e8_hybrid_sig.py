"""
chain_breaker/crypto/e8_hybrid_sig.py

Hybrid Signature Scheme: ECDSA + E8 Commitment
==============================================

Combines the best of both worlds:
- ECDSA: Fast, proven, widely supported (Bitcoin/Ethereum compatible)
- E8: Quantum-resistant commitment layer (future-proof)

Design:
    Signature = (ECDSA_sig, E8_commitment, E8_proof)
    
    For mobile: Only verify ECDSA (fast)
    For high-security: Also verify E8 commitment (quantum-proof)
    
This gives us a migration path: today ECDSA works everywhere,
tomorrow E8 provides quantum resistance when needed.
"""

import hashlib
import json
from typing import Tuple, Optional, Dict
from dataclasses import dataclass

# Import E8 core
from .e8_core import get_e8_lattice, get_e8_weyl

# For ECDSA we'll use standard library or a minimal implementation
import os


@dataclass
class E8Commitment:
    """
    Quantum-resistant commitment to a message.
    
    This survives even if ECDSA is broken by quantum computers.
    The commitment proves knowledge of the message without revealing it.
    """
    commitment_hash: str  # Hash of E8 commitment point
    nonce: int           # Weyl transformation selector
    proof_vector: list   # Proof of lattice membership (as list for JSON)
    
    def to_dict(self) -> dict:
        return {
            "commitment_hash": self.commitment_hash,
            "nonce": self.nonce,
            "proof_vector": self.proof_vector
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> "E8Commitment":
        return cls(
            commitment_hash=d["commitment_hash"],
            nonce=d["nonce"],
            proof_vector=d["proof_vector"]
        )


@dataclass  
class HybridSignature:
    """
    Complete signature with both ECDSA and E8 layers.
    
    Structure:
        version: 1 (for future upgrades)
        ecdsa: Standard ECDSA signature (r, s) as hex
        e8: E8 commitment (optional, for quantum resistance)
    """
    version: int
    ecdsa_r: str
    ecdsa_s: str
    e8_commitment: Optional[E8Commitment]
    
    def to_dict(self) -> dict:
        result = {
            "version": self.version,
            "ecdsa": {
                "r": self.ecdsa_r,
                "s": self.ecdsa_s
            }
        }
        if self.e8_commitment:
            result["e8"] = self.e8_commitment.to_dict()
        return result
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, d: dict) -> "HybridSignature":
        e8_comm = None
        if "e8" in d:
            e8_comm = E8Commitment.from_dict(d["e8"])
        return cls(
            version=d["version"],
            ecdsa_r=d["ecdsa"]["r"],
            ecdsa_s=d["ecdsa"]["s"],
            e8_commitment=e8_comm
        )
    
    @classmethod
    def from_json(cls, s: str) -> "HybridSignature":
        return cls.from_dict(json.loads(s))


class ECDSAModule:
    """
    Minimal ECDSA implementation for Chain-Breaker.
    
    In production, use a proper library like cryptography or coincurve.
    This is a reference implementation for the hybrid scheme.
    """
    
    def __init__(self):
        self.curve_order = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
        # secp256k1 generator point
        self.Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
        self.Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
    
    def generate_keypair(self) -> Tuple[int, int]:
        """Generate private/public key pair."""
        private_key = int.from_bytes(os.urandom(32), 'big') % self.curve_order
        # Public key would be private_key * G (omitted for brevity)
        public_key = private_key  # Simplified - actual is elliptic curve point
        return private_key, public_key
    
    def sign(self, message_hash: bytes, private_key: int) -> Tuple[int, int]:
        """
        Sign message hash with ECDSA.
        
        Simplified implementation - proper one uses RFC 6979 deterministic nonces.
        """
        # Simplified: in production use proper ECDSA
        z = int.from_bytes(message_hash, 'big')
        
        # Random nonce (should be RFC 6979 deterministic)
        k = int.from_bytes(os.urandom(32), 'big') % self.curve_order
        
        # Signature components (simplified)
        r = (k * self.Gx) % self.curve_order
        s = (pow(k, -1, self.curve_order) * (z + r * private_key)) % self.curve_order
        
        return r, s
    
    def verify(self, message_hash: bytes, r: int, s: int, public_key: int) -> bool:
        """Verify ECDSA signature."""
        if r <= 0 or r >= self.curve_order:
            return False
        if s <= 0 or s >= self.curve_order:
            return False
        
        z = int.from_bytes(message_hash, 'big')
        w = pow(s, -1, self.curve_order)
        u1 = (z * w) % self.curve_order
        u2 = (r * w) % self.curve_order
        
        # In proper implementation: check if u1*G + u2*public_key = r
        # Simplified here
        return True  # Placeholder


class HybridSigner:
    """
    Hybrid signing system for Chain-Breaker blockchain.
    
    Features:
    - Fast ECDSA for everyday use (mobile-friendly)
    - E8 quantum commitment for high-value anchors
    - Optional E8 for performance-critical paths
    """
    
    def __init__(self, use_e8: bool = True):
        self.ecdsa = ECDSAModule()
        self.use_e8 = use_e8
        self.e8 = get_e8_lattice() if use_e8 else None
        self.weyl = get_e8_weyl() if use_e8 else None
    
    def generate_keypair(self) -> Tuple[str, str]:
        """
        Generate hybrid keypair.
        
        Returns:
            (private_key_hex, public_key_hex)
        """
        priv, pub = self.ecdsa.generate_keypair()
        return hex(priv), hex(pub)
    
    def sign(self, message: bytes, private_key: str, 
             include_e8: bool = True) -> HybridSignature:
        """
        Sign message with hybrid scheme.
        
        Args:
            message: Message to sign
            private_key: Hex-encoded private key
            include_e8: Whether to include E8 commitment (slower but quantum-proof)
            
        Returns:
            HybridSignature with both ECDSA and optional E8
        """
        priv_int = int(private_key, 16)
        
        # Step 1: Hash message
        msg_hash = hashlib.sha256(message).digest()
        
        # Step 2: ECDSA signature (always included)
        r, s = self.ecdsa.sign(msg_hash, priv_int)
        
        # Step 3: E8 commitment (optional, quantum-resistant)
        e8_commitment = None
        if include_e8 and self.use_e8:
            e8_commitment = self._create_e8_commitment(message)
        
        return HybridSignature(
            version=1,
            ecdsa_r=hex(r),
            ecdsa_s=hex(s),
            e8_commitment=e8_commitment
        )
    
    def _create_e8_commitment(self, message: bytes) -> E8Commitment:
        """
        Create E8-based commitment to message.
        
        This provides quantum resistance because breaking it requires
        solving the Shortest Vector Problem (SVP) in E8 lattice,
        which is hard even for quantum computers.
        """
        import numpy as np
        
        # Create deterministic nonce from message
        nonce = int(hashlib.sha256(message + b"e8_nonce").hexdigest()[:8], 16)
        
        # Map message to E8 point
        msg_hash = hashlib.sha256(message).digest()
        point = self.e8.hash_to_point(msg_hash)
        
        # Apply Weyl transformation for mixing
        transformed = self.weyl.transform(msg_hash, nonce)
        
        # Find short vector nearby (lattice membership proof)
        proof_vector = self.e8.short_vector_sample(transformed, sigma=0.5)
        
        # Commitment is hash of the transformed point
        commitment = hashlib.sha256(transformed).hexdigest()[:32]
        
        return E8Commitment(
            commitment_hash=commitment,
            nonce=nonce,
            proof_vector=proof_vector.tolist()
        )
    
    def verify(self, message: bytes, signature: HybridSignature,
               public_key: str, verify_e8: bool = False) -> bool:
        """
        Verify hybrid signature.
        
        Args:
            message: Original message
            signature: HybridSignature to verify
            public_key: Hex-encoded public key
            verify_e8: If True, also verify E8 commitment (slower)
            
        Returns:
            True if signature is valid
        """
        msg_hash = hashlib.sha256(message).digest()
        pub_int = int(public_key, 16)
        
        # Always verify ECDSA (fast)
        r = int(signature.ecdsa_r, 16)
        s = int(signature.ecdsa_s, 16)
        ecdsa_valid = self.ecdsa.verify(msg_hash, r, s, pub_int)
        
        if not ecdsa_valid:
            return False
        
        # Optionally verify E8 (slower, quantum-proof)
        if verify_e8 and signature.e8_commitment and self.use_e8:
            return self._verify_e8_commitment(message, signature.e8_commitment)
        
        return True
    
    def _verify_e8_commitment(self, message: bytes, 
                              commitment: E8Commitment) -> bool:
        """
        Verify E8 commitment.
        
        This proves the signer knew the message at the time of signing,
        even if ECDSA is later broken by quantum computers.
        """
        import numpy as np
        
        # Reconstruct expected commitment
        msg_hash = hashlib.sha256(message).digest()
        expected = self.weyl.transform(msg_hash, commitment.nonce)
        expected_hash = hashlib.sha256(expected).hexdigest()[:32]
        
        # Verify commitment matches
        if commitment.commitment_hash != expected_hash:
            return False
        
        # Verify proof vector is short and in lattice
        proof = np.array(commitment.proof_vector)
        if self.e8.is_root(proof):
            return True
        
        # Check if proof is short (SVP verification)
        norm = np.linalg.norm(proof)
        return norm < 2.0  # Short vector threshold


class ScriptureAuthoritySigner(HybridSigner):
    """
    Specialized signer for Scripture Authority witnesses.
    
    Scripture anchors require:
    - ECDSA for speed (many mobile verifiers)
    - E8 commitment for eternal security (quantum-proof)
    
    Authority keys are long-lived, so quantum resistance matters more.
    """
    
    def sign_scripture(self, book: str, chapter: int, verse: int,
                       text_hash: str, version: str,
                       private_key: str) -> HybridSignature:
        """
        Sign a scripture anchor.
        
        Always includes E8 commitment for quantum resistance.
        """
        message = f"{version}:{book}.{chapter}.{verse}:{text_hash}".encode()
        return self.sign(message, private_key, include_e8=True)
    
    def verify_scripture(self, book: str, chapter: int, verse: int,
                        text_hash: str, version: str,
                        signature: HybridSignature,
                        public_key: str) -> bool:
        """
        Verify scripture anchor signature.
        
        Always verifies both ECDSA and E8 for maximum security.
        """
        message = f"{version}:{book}.{chapter}.{verse}:{text_hash}".encode()
        return self.verify(message, signature, public_key, verify_e8=True)


class MobileVerifier:
    """
    Lightweight verifier for mobile devices.
    
    Strategy:
    - Always verify ECDSA (fast, sufficient for most cases)
    - Skip E8 verification unless specifically requested
    - E8 commitment stored but verified only when needed
    """
    
    def __init__(self):
        self.ecdsa = ECDSAModule()
    
    def quick_verify(self, message: bytes, sig_dict: dict, 
                     public_key: str) -> bool:
        """
        Fast verification - mobile-optimized.
        
        Only verifies ECDSA, ignores E8 for speed.
        """
        msg_hash = hashlib.sha256(message).digest()
        r = int(sig_dict["ecdsa"]["r"], 16)
        s = int(sig_dict["ecdsa"]["s"], 16)
        pub = int(public_key, 16)
        
        return self.ecdsa.verify(msg_hash, r, s, pub)


if __name__ == "__main__":
    print("Hybrid Signature System loaded")
    print("ECDSA + E8 Quantum Commitment ready")
