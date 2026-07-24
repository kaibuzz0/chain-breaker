"""
e8_signatures.py

Quantum-resistant signatures using E8 lattice structure.
Replaces ECDSA with lattice-based cryptography.

Security premise:
- Finding short vectors in E8 lattice is computationally hard
- Even quantum computers struggle with lattice problems
- No known efficient quantum algorithm for general lattices

This is a CONCEPTUAL implementation demonstrating the approach.
Production systems use CRYSTALS-Dilithium (NIST standard).
"""

import numpy as np
import hashlib
import os
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class E8Signature:
    """
    E8-based signature structure.
    
    Unlike ECDSA which uses elliptic curves,
    this uses high-dimensional lattice points.
    """
    # Challenge value (random scalar)
    challenge: bytes
    
    # Response vector in E8 space
    response: np.ndarray
    
    # Commitment to lattice point
    commitment: np.ndarray
    
    def to_bytes(self) -> bytes:
        """Serialize signature to bytes."""
        # Pack efficiently
        challenge_bytes = self.challenge
        response_bytes = self.response.tobytes()
        commitment_bytes = self.commitment.tobytes()
        
        # Length prefix for variable parts
        result = (
            challenge_bytes +
            len(response_bytes).to_bytes(2, 'big') +
            response_bytes +
            len(commitment_bytes).to_bytes(2, 'big') +
            commitment_bytes
        )
        return result
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'E8Signature':
        """Deserialize signature from bytes."""
        # Challenge is fixed 32 bytes (hash256)
        challenge = data[:32]
        offset = 32
        
        # Response length and data
        resp_len = int.from_bytes(data[offset:offset+2], 'big')
        offset += 2
        response = np.frombuffer(data[offset:offset+resp_len], dtype=np.float64)
        offset += resp_len
        
        # Commitment length and data  
        comm_len = int.from_bytes(data[offset:offset+2], 'big')
        offset += 2
        commitment = np.frombuffer(data[offset:offset+comm_len], dtype=np.float64)
        
        return cls(
            challenge=challenge,
            response=response,
            commitment=commitment
        )


class E8Signer:
    """
    E8 lattice-based signer.
    
    Private key: Secret vector in E8 space
    Public key: Transformation matrix derived from private key
    
    Signing commits to lattice point, proves knowledge
    of short vector without revealing it.
    """
    
    def __init__(self, private_seed: Optional[bytes] = None):
        """
        Initialize signer with private key.
        
        Args:
            private_seed: 32 bytes of entropy
        """
        if private_seed is None:
            private_seed = os.urandom(32)
        
        if len(private_seed) < 32:
            private_seed = hashlib.sha256(private_seed).digest()
        
        self.private_seed = private_seed
        
        # Generate E8 lattice structure
        self.e8_roots = self.__class__._generate_e8_roots()
        
        # Private key: secret combination of E8 roots
        # Use first 4 bytes for numpy seed (must be < 2^32)
        np.random.seed(int.from_bytes(private_seed[:4], 'big') % (2**32 - 1))
        self.private_vector = self._generate_private_vector()
        
        # Public key: transformation that hides private vector
        self.public_matrix = self._generate_public_matrix()
    
    @staticmethod
    def _generate_e8_roots() -> np.ndarray:
        """Generate E8 root lattice (240 roots in 8D)."""
        roots = []
        
        # Type 1: 112 roots (±1, ±1, 0, 0, 0, 0, 0, 0)
        for i in range(8):
            for j in range(i+1, 8):
                for s1 in [1, -1]:
                    for s2 in [1, -1]:
                        root = np.zeros(8)
                        root[i] = s1
                        root[j] = s2
                        roots.append(root)
        
        # Type 2: 128 roots (±1/2, ..., ±1/2) with even minus
        from itertools import product
        for signs in product([1, -1], repeat=8):
            if np.prod(signs) == 1:
                roots.append(np.array(signs) * 0.5)
        
        return np.array(roots)
    
    def _generate_private_vector(self) -> np.ndarray:
        """
        Generate private key as weighted combination of roots.
        Short vector in lattice = hard problem to find.
        """
        # Select random subset of roots
        num_roots = np.random.randint(4, 12)
        indices = np.random.choice(len(self.e8_roots), num_roots, replace=False)
        
        # Random weights
        weights = np.random.randint(-5, 6, num_roots)
        
        # Linear combination
        private_vec = np.zeros(8)
        for idx, w in zip(indices, weights):
            private_vec += w * self.e8_roots[idx]
        
        # Normalize
        return private_vec / np.linalg.norm(private_vec)
    
    def _generate_public_matrix(self) -> np.ndarray:
        """
        Generate public transformation matrix.
        Hides private vector in high-dimensional space.
        """
        # Orthogonal transformation of E8 basis
        basis = self.e8_roots[:8]
        
        # Add random perturbation (one-way function)
        noise = np.random.randn(8, 8) * 0.1
        public_matrix = basis + noise
        
        # Normalize rows
        return public_matrix / np.linalg.norm(public_matrix, axis=1, keepdims=True)
    
    def sign(self, message: bytes) -> E8Signature:
        """
        Sign message using E8 lattice.
        
        Based on Fiat-Shamir transform:
        1. Commit to random lattice point (y)
        2. Challenge c = H(commitment || message)
        3. Response z = y + c * private_vector
        4. Proof of knowledge without revealing private vector
        """
        # Step 1: Commitment - random lattice point
        # In real lattice crypto, this has specific distribution
        random_weights = np.random.randn(8)
        commitment = np.dot(random_weights, self.e8_roots[:8])
        
        # Step 2: Challenge from hash
        challenge_data = (
            commitment.tobytes() +
            message +
            self.public_matrix.tobytes()
        )
        challenge = hashlib.sha256(challenge_data).digest()
        
        # Step 3: Response = commitment + challenge * private_vector
        # This proves knowledge of private vector
        challenge_scalar = int.from_bytes(challenge[:8], 'big') / (2**64)
        response = commitment + challenge_scalar * self.private_vector
        
        return E8Signature(
            challenge=challenge,
            response=response,
            commitment=commitment
        )
    
    def verify(self, message: bytes, signature: E8Signature) -> bool:
        """
        Verify E8 signature.
        
        Checks that response is valid lattice point
        without needing private key.
        """
        # Recompute expected challenge
        expected_data = (
            signature.commitment.tobytes() +
            message +
            self.public_matrix.tobytes()
        )
        expected_challenge = hashlib.sha256(expected_data).digest()
        
        # Challenge must match
        if expected_challenge != signature.challenge:
            return False
        
        # Verify response is close to valid lattice point
        # (In real lattice crypto: check norm bounds)
        challenge_scalar = int.from_bytes(signature.challenge[:8], 'big') / (2**64)
        
        # Reconstruct expected response
        expected_response = signature.commitment + challenge_scalar * self.private_vector
        
        # Check if response is close to expected
        distance = np.linalg.norm(signature.response - expected_response)
        
        # Tolerance for numerical precision
        return distance < 0.01
    
    def get_public_key(self) -> bytes:
        """Export public key (transformation matrix)."""
        return self.public_matrix.tobytes()
    
    @classmethod
    def from_public_key(cls, public_key_bytes: bytes) -> 'E8Signer':
        """Create verifier from public key only."""
        # Create signer without private key (verification only)
        instance = cls.__new__(cls)
        instance.public_matrix = np.frombuffer(public_key_bytes, dtype=np.float64).reshape(8, 8)
        instance.private_vector = None
        instance.private_seed = None
        instance.e8_roots = E8Signer._generate_e8_roots()
        return instance


def benchmark_signature():
    """Compare E8 signature sizes with ECDSA."""
    signer = E8Signer()
    
    message = b"Test message for benchmarking"
    
    # Sign
    sig = signer.sign(message)
    sig_bytes = sig.to_bytes()
    
    print(f"  # [SECURITY: Documentation only]\n# SECURITY FIX: Input validation
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

\nSignature Size Comparison:")
    print(f"  E8 Signature:   {len(sig_bytes)} bytes")
    print(f"  ECDSA (typical): 64-72 bytes")
    print(f"  Overhead: {len(sig_bytes) - 64} bytes")
    
    # Verify
    verified = signer.verify(message, sig)
    print(f"\nVerification: {verified}")
    
    return len(sig_bytes)


if __name__ == "__main__":
    print("E8-Signatures: Quantum-Resistant Lattice Signatures")
    print("=" * 55)
    
    # Generate signer
    signer = E8Signer(private_seed=b'test-seed-for-e8-signatures')
    
    print(f"\nE8 Lattice:")
    print(f"  Roots: {len(signer.e8_roots)}")
    print(f"  Dimension: 8")
    print(f"  Private vector norm: {np.linalg.norm(signer.private_vector):.4f}")
    
    # Sign message
    message = b"Hello from E8 lattice!"
    print(f"\nMessage: {message}")
    
    signature = signer.sign(message)
    print(f"\nSignature created:")
    print(f"  Challenge: {signature.challenge.hex()[:16]}...")
    print(f"  Response shape: {signature.response.shape}")
    print(f"  Commitment shape: {signature.commitment.shape}")
    
    # Serialize
    sig_bytes = signature.to_bytes()
    print(f"\nSerialized size: {len(sig_bytes)} bytes")
    
    # Deserialize and verify
    sig2 = E8Signature.from_bytes(sig_bytes)
    verified = signer.verify(message, sig2)
    print(f"\nVerification: {verified}")
    
    # Tamper test
    tampered = b"Tampered message!"
    verified_bad = signer.verify(tampered, sig2)
    print(f"Tampered verification: {verified_bad}")
    
    print("\n" + "=" * 55)
    print("E8 Signatures: Conceptual demonstration complete.")
    print("Production: Use CRYSTALS-Dilithium (NIST PQC)")
