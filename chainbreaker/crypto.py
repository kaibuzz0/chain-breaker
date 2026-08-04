
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
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

Hash = str  # 64-char lowercase hex SHA-256 digest

# Protocol v2 target bounds (256-bit unsigned integers).
MAX_TARGET = 0x0000FFFF00000000000000000000000000000000000000000000000000000000
MIN_TARGET = 1


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
    def hash_single(cls, data: bytes) -> bytes:
        """Single SHA-256 digest."""
        return cls.sha256(data)

    @classmethod
    def hash_single_hex(cls, data: bytes) -> Hash:
        return cls.hex(cls.hash_single(data))

    @classmethod
    def hash_double(cls, data: bytes) -> bytes:
        """Double SHA-256 digest (Bitcoin style)."""
        return cls.double_sha256(data)

    @classmethod
    def hash_double_hex(cls, data: bytes) -> Hash:
        return cls.hex(cls.hash_double(data))

    @classmethod
    def canonical_json(cls, obj: Any) -> bytes:
        """Return canonical UTF-8 JSON bytes with sorted keys."""
        if is_dataclass(obj) and not isinstance(obj, type):
            obj = asdict(obj)
        return json.dumps(
            obj,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    @classmethod
    def hash_object(cls, obj: Any) -> bytes:
        """Single SHA-256 digest of the canonical JSON of an object."""
        return cls.sha256(cls.canonical_json(obj))

    @classmethod
    def hash_object_hex(cls, obj: Any) -> Hash:
        return cls.hex(cls.hash_object(obj))


class MerkleTree:
    """Binary Merkle tree over a list of byte leaves.

    Uses double-SHA256 for internal hashing to match Bitcoin convention.
    Duplicate last leaf when level length is odd.
    """

    def __init__(self, leaves: list[bytes]):
        self.leaves = leaves
        self.levels: list[list[bytes]] = []
        if leaves:
            self.levels = self._build(leaves)

    def _build(self, leaves: list[bytes]) -> list[list[bytes]]:
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
    def root(self) -> bytes | None:
        if not self.levels:
            return None
        return self.levels[-1][0]

    def get_proof(self, index: int) -> list[bytes]:
        proof = []
        for level in self.levels[:-1]:
            sibling = index + 1 if index % 2 == 0 else index - 1
            proof.append(level[sibling] if sibling < len(level) else level[index])
            index //= 2
        return proof

    @staticmethod
    def verify_proof(root: bytes, leaf: bytes, proof: list[bytes], index: int) -> bool:
        current = leaf
        for sibling in proof:
            if index % 2 == 0:
                current = HashEngine.double_sha256(current + sibling)
            else:
                current = HashEngine.double_sha256(sibling + current)
            index //= 2
        return current == root


def target_to_hex(target: int) -> str:
    return target.to_bytes(32, "big").hex()


def hex_to_target(hex_target: str) -> int:
    return int.from_bytes(bytes.fromhex(hex_target), "big")


def work_for_target(target: int) -> float:
    """Approximate work represented by a target."""
    if target <= 0:
        raise ValueError("target must be positive")
    return (2**256 - target) / (target + 1)


def work_for_target_v2(target: int) -> int:
    """Exact integer work represented by a target for Protocol v2.

    Defined as floor(MAX_TARGET / target).  Returns a positive integer for any
    valid target in (0, MAX_TARGET].
    """
    if target <= 0:
        raise ValueError("target must be positive")
    return MAX_TARGET // target


def check_pow_v2(header_bytes: bytes, target: int) -> bool:
    """Verify v2 PoW against canonical 149-byte header bytes."""
    if len(header_bytes) != 149:
        return False
    if target <= 0:
        return False
    digest = HashEngine.hash_double(header_bytes)
    return int.from_bytes(digest, "big") <= target


def target_to_difficulty(target: int) -> float:
    return 0x00000000FFFF0000000000000000000000000000000000000000000000000000 / target


def difficulty_to_target(difficulty: float) -> int:
    return int(0x00000000FFFF0000000000000000000000000000000000000000000000000000 / difficulty)


def encode_public_key(pk: Ed25519PublicKey) -> str:
    return pk.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def decode_public_key(hex_key: str) -> Ed25519PublicKey:
    raw = bytes.fromhex(hex_key)
    if len(raw) != 32:
        raise ValueError("Ed25519 public key must be 32 bytes")
    return Ed25519PublicKey.from_public_bytes(raw)


def encode_private_key(sk: Ed25519PrivateKey) -> str:
    return sk.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()


def decode_private_key(hex_key: str) -> Ed25519PrivateKey:
    raw = bytes.fromhex(hex_key)
    if len(raw) != 32:
        raise ValueError("Ed25519 private key must be 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(raw)


def generate_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    sk = Ed25519PrivateKey.generate()
    return sk, sk.public_key()


def sign(sk: Ed25519PrivateKey, message: bytes) -> str:
    return sk.sign(message).hex()


def verify(pk: Ed25519PublicKey, message: bytes, signature_hex: str) -> bool:
    try:
        raw = bytes.fromhex(signature_hex)
        if len(raw) != 64:
            return False
        pk.verify(raw, message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def make_curator_signature(sk: Ed25519PrivateKey, body_without_witness: dict[str, Any]) -> str:
    """Return a curator signature over a governance transaction body.

    The signed message matches the one checked by the registry reducer's
    `_verify_curator_signature`, ensuring CLI-generated rotate/revoke
    transactions are accepted by the consensus layer.
    """
    from .governance import NETWORK_ID as _GOV_NETWORK_ID
    from .governance import PROTOCOL_VERSION as _GOV_PROTOCOL_VERSION

    message = HashEngine.hash_object({
        "network_id": _GOV_NETWORK_ID,
        "version": _GOV_PROTOCOL_VERSION,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body_without_witness),
    })
    return sign(sk, message)
