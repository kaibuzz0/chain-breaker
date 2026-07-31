
"""Cryptographic primitives for Chain-Breaker.

- SHA-256 / double SHA-256
- Deterministic Merkle tree (Bitcoin style)
- Canonical JSON serialization for hashing
- Ed25519 wrappers using the `cryptography` library
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any, List, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature


Hash = str  # 64-char lowercase hex SHA-256 digest


class HashEngine:
    """Deterministic SHA-256 helpers."""

    @staticmethod
    def sha256(data: bytes) -> bytes:
        return hashlib.sha256(data).digest()

    @staticmethod
    def double_sha256(data: bytes) -> bytes:
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()

    @staticmethod
    def hex(data: bytes) -> str:
        return data.hex()

    @classmethod
    def hash_bytes(cls, data: bytes) -> Hash:
        return cls.hex(cls.sha256(data))

    @classmethod
    def canonical_json(cls, obj: Any) -> bytes:
        """Return canonical UTF-8 JSON bytes with sorted keys."""
        if is_dataclass(obj) and not isinstance(obj, type):
            obj = asdict(obj)
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def hash_object(cls, obj: Any) -> bytes:
        return cls.sha256(cls.canonical_json(obj))

    @classmethod
    def hash_object_hex(cls, obj: Any) -> Hash:
        return cls.hash_bytes(cls.canonical_json(obj))


class MerkleTree:
    """Binary Merkle tree over a list of byte leaves.

    Uses double-SHA256 for internal hashing to match Bitcoin convention.
    Duplicate last leaf when level length is odd.
    """

    def __init__(self, leaves: List[bytes]):
        self.leaves = leaves
        self.levels: List[List[bytes]] = []
        if leaves:
            self.levels = self._build(leaves)

    def _build(self, leaves: List[bytes]) -> List[List[bytes]]:
        levels = [list(leaves)]
        current = levels[0]
        while len(current) > 1:
            next_level = []
            for i in range(0, len(current), 2):
                left = current[i]
                right = current[i + 1] if i + 1 < len(current) else left
                next_level.append(HashEngine.double_sha256(left + right))
            current = next_level
            levels.append(current)
        return levels

    @property
    def root(self) -> Optional[bytes]:
        if not self.levels:
            return None
        return self.levels[-1][0]

    def get_proof(self, index: int) -> List[bytes]:
        proof = []
        for level in self.levels[:-1]:
            sibling = index + 1 if index % 2 == 0 else index - 1
            proof.append(level[sibling] if sibling < len(level) else level[index])
            index //= 2
        return proof

    @staticmethod
    def verify_proof(root: bytes, leaf: bytes, proof: List[bytes], index: int) -> bool:
        current = leaf
        for sibling in proof:
            if index % 2 == 0:
                current = HashEngine.double_sha256(current + sibling)
            else:
                current = HashEngine.double_sha256(sibling + current)
            index //= 2
        return current == root


def encode_public_key(pk: Ed25519PublicKey) -> str:
    return pk.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def decode_public_key(hex_key: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(bytes.fromhex(hex_key))


def encode_private_key(sk: Ed25519PrivateKey) -> str:
    return sk.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()


def decode_private_key(hex_key: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(hex_key))


def generate_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    sk = Ed25519PrivateKey.generate()
    return sk, sk.public_key()


def sign(sk: Ed25519PrivateKey, message: bytes) -> str:
    return sk.sign(message).hex()


def verify(pk: Ed25519PublicKey, message: bytes, signature_hex: str) -> bool:
    try:
        pk.verify(bytes.fromhex(signature_hex), message)
        return True
    except InvalidSignature:
        return False
