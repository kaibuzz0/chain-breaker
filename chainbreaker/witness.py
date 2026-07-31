
"""Curator / witness registry and attestation verification."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .crypto import (
    HashEngine,
    encode_public_key,
    decode_public_key,
    sign,
    verify,
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


class WitnessError(ValueError):
    """Raised when witness data is invalid."""


@dataclass
class Curator:
    curator_id: str
    public_key_hex: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class Registry:
    """Immutable-in-memory curator registry."""

    def __init__(self, curators: Optional[List[Curator]] = None):
        self._by_id: Dict[str, Curator] = {}
        for c in curators or []:
            if c.curator_id in self._by_id:
                raise WitnessError(f"duplicate curator id: {c.curator_id}")
            self._by_id[c.curator_id] = c

    def get(self, curator_id: str) -> Optional[Curator]:
        return self._by_id.get(curator_id)

    def list(self) -> List[Curator]:
        return list(self._by_id.values())

    def register(self, curator: Curator) -> None:
        if curator.curator_id in self._by_id:
            raise WitnessError(f"duplicate curator id: {curator.curator_id}")
        self._by_id[curator.curator_id] = curator


def make_attestation_message(network_id: str, version: int,
                             body_hash: str, curator_id: str,
                             timestamp: int) -> bytes:
    msg = {
        "network_id": network_id,
        "version": version,
        "body_hash": body_hash,
        "curator_id": curator_id,
        "timestamp": timestamp,
    }
    return HashEngine.canonical_json(msg)


class Witness:
    def __init__(self, curator_id: str, timestamp: int, signature_hex: str):
        self.curator_id = curator_id
        self.timestamp = timestamp
        self.signature_hex = signature_hex

    def to_dict(self) -> Dict[str, Any]:
        return {
            "curator_id": self.curator_id,
            "timestamp": self.timestamp,
            "signature": self.signature_hex,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Witness:
        return cls(
            curator_id=str(data["curator_id"]),
            timestamp=int(data["timestamp"]),
            signature_hex=str(data["signature"]),
        )


def sign_transaction(
    private_key: Ed25519PrivateKey,
    curator_id: str,
    tx: Dict[str, Any],
    network_id: str,
) -> Witness:
    version = int(tx["version"])
    body_hash = HashEngine.hash_object_hex(tx["body"])
    timestamp = int(time.time())
    message = make_attestation_message(network_id, version, body_hash, curator_id, timestamp)
    return Witness(curator_id=curator_id, timestamp=timestamp, signature_hex=sign(private_key, message))


def verify_witness(
    witness: Witness,
    tx: Dict[str, Any],
    registry: Registry,
    network_id: str,
    max_age_seconds: int = 86400,
    now: Optional[int] = None,
) -> bool:
    curator = registry.get(witness.curator_id)
    if curator is None:
        return False

    version = int(tx["version"])
    body_hash = HashEngine.hash_object_hex(tx["body"])
    message = make_attestation_message(network_id, version, body_hash,
                                       witness.curator_id, witness.timestamp)
    try:
        pk = decode_public_key(curator.public_key_hex)
    except Exception:
        return False
    if not verify(pk, message, witness.signature_hex):
        return False

    now = now or int(time.time())
    if abs(now - witness.timestamp) > max_age_seconds:
        return False
    return True


def verify_transaction_witnesses(
    tx: Dict[str, Any],
    registry: Registry,
    network_id: str,
    required: int = 1,
    **kwargs: Any,
) -> bool:
    witnesses_raw = tx.get("witnesses", [])
    if len(witnesses_raw) < required:
        return False

    seen: Set[str] = set()
    valid = 0
    for w in witnesses_raw:
        witness = Witness.from_dict(w)
        if witness.curator_id in seen:
            return False
        seen.add(witness.curator_id)
        if verify_witness(witness, tx, registry, network_id, **kwargs):
            valid += 1

    return valid >= required
