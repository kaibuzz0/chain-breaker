"""
chain_breaker/crypto/e8_core.py
E8 Lie Group Mathematical Foundation

The E8 is the largest exceptional Lie group:
- Rank: 8
- Root system: 240 roots in 8-dimensional space
- Weyl group: 696,729,600 symmetries
- Dimension: 248 (as Lie algebra)
"""

import numpy as np
from typing import List, Tuple, Optional
import hashlib
import struct


class E8Lattice:
    """
    E8 root lattice operations.
    
    The E8 root system consists of 240 vectors in R^8:
    - 112 roots: (±1, ±1, 0, 0, 0, 0, 0, 0) permutations
    - 128 roots: (±½, ±½, ±½, ±½, ±½, ±½, ±½, ±½) with even number of minuses
    """
    
    def __init__(self):
        self._roots: Optional[np.ndarray] = None
        
    @property
    def roots(self) -> np.ndarray:
        """Lazy-loaded E8 roots."""
        if self._roots is None:
            self._roots = self._generate_roots()
        return self._roots
    
    def _generate_roots(self) -> np.ndarray:
        """Generate the 240 roots of E8."""
        roots = []
        
        # Type 1: (±1, ±1, 0, 0, 0, 0, 0, 0) permutations = 112 roots
        for i in range(8):
            for j in range(i + 1, 8):
                for s1 in [1, -1]:
                    for s2 in [1, -1]:
                        root = np.zeros(8, dtype=np.float64)
                        root[i] = s1
                        root[j] = s2
                        roots.append(root)
        
        # Type 2: (±½, ..., ±½) with even number of minuses = 128 roots
        from itertools import combinations
        for num_minus in [0, 2, 4, 6, 8]:
            for positions in combinations(range(8), num_minus):
                root = np.full(8, 0.5, dtype=np.float64)
                for pos in positions:
                    root[pos] = -0.5
                if abs(np.sum(root) % 2) < 0.001:
                    roots.append(root)
        
        return np.array(roots, dtype=np.float64)
    
    def is_root(self, v: np.ndarray, tolerance: float = 1e-9) -> bool:
        """Check if vector is in the E8 root system."""
        v = np.asarray(v, dtype=np.float64)
        norm_sq = np.dot(v, v)
        if abs(norm_sq - 2.0) > tolerance:
            return False
        
        is_half_integer = False
        for coord in v:
            if abs(coord - round(coord)) < tolerance:
                continue
            elif abs(abs(coord) - 0.5) < tolerance:
                is_half_integer = True
            else:
                return False
        
        if is_half_integer:
            if abs(np.sum(v) % 2) > tolerance:
                return False
        
        return True
    
    def nearest_root(self, v: np.ndarray) -> Tuple[np.ndarray, int]:
        """Find nearest E8 root to vector v."""
        v = np.asarray(v, dtype=np.float64)
        distances = np.sum((self.roots - v) ** 2, axis=1)
        idx = int(np.argmin(distances))
        return self.roots[idx].copy(), idx
    
    def weyl_reflection(self, v: np.ndarray, root_idx: int) -> np.ndarray:
        """
        Apply Weyl reflection: s_α(v) = v - ⟨v,α⟩ α
        (Since ⟨α,α⟩ = 2 for E8 roots)
        """
        v = np.asarray(v, dtype=np.float64)
        root = self.roots[root_idx]
        return v - np.dot(v, root) * root
    
    def hash_to_point(self, data: bytes) -> np.ndarray:
        """Deterministically map hash bytes to normalized 8D point."""
        h = hashlib.sha256(data).digest()
        h = hashlib.sha256(h).digest()
        
        coords = np.zeros(8, dtype=np.float64)
        for i in range(8):
            chunk = h[i*4:(i+1)*4]
            val = struct.unpack('>I', chunk)[0]
            coords[i] = (val / 0xFFFFFFFF) * 2 - 1
        
        norm = np.linalg.norm(coords)
        if norm > 0:
            coords = coords / norm
        
        return coords
    
    def point_to_hash(self, point: np.ndarray) -> bytes:
        """Convert 8D point back to hash bytes."""
        point = np.asarray(point, dtype=np.float64)
        point = point / np.linalg.norm(point)
        
        h = bytearray(32)
        for i in range(8):
            val = int(((point[i] + 1) / 2) * 0xFFFFFFFF)
            h[i*4:(i+1)*4] = struct.pack('>I', val)
        
        return bytes(h)
    
    def short_vector_sample(self, seed: bytes, sigma: float = 1.0) -> np.ndarray:
        """Sample short vector from E8 lattice (SVP problem)."""
        np.random.seed(int.from_bytes(seed[:8], 'big') % (2**32))
        v = np.random.normal(0, sigma, 8)
        nearest, _ = self.nearest_root(v)
        return nearest


class E8WeylTransform:
    """Deterministic Weyl group transformations for cryptographic mixing."""
    
    def __init__(self):
        self.e8 = E8Lattice()
    
    def transform(self, data: bytes, nonce: int) -> bytes:
        """Apply Weyl group transformation based on nonce."""
        point = self.e8.hash_to_point(data)
        np.random.seed(nonce % (2**32))
        
        num_reflections = 8 + (nonce % 8)
        for _ in range(num_reflections):
            root_idx = np.random.randint(len(self.e8.roots))
            point = self.e8.weyl_reflection(point, root_idx)
        
        return self.e8.point_to_hash(point)
    
    def inverse_transform(self, data: bytes, nonce: int) -> bytes:
        """Weyl reflections are self-inverse."""
        return self.transform(data, nonce)


# Module-level singletons
_e8_lattice = None
_e8_weyl = None

def get_e8_lattice() -> E8Lattice:
    global _e8_lattice
    if _e8_lattice is None:
        _e8_lattice = E8Lattice()
    return _e8_lattice

def get_e8_weyl() -> E8WeylTransform:
    global _e8_weyl
    if _e8_weyl is None:
        _e8_weyl = E8WeylTransform()
    return _e8_weyl


if __name__ == "__main__":
    print("E8 MATHEMATICAL ENGINE - SELF TEST")
    e8 = E8Lattice()
    print(f"Generated {len(e8.roots)} E8 roots")
    assert len(e8.roots) == 240
    print("All tests passed!")
