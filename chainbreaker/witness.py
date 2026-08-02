
"""Curator registry and attestation logic."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .block import NETWORK_ID
from .codec import validate_transaction
from .crypto import (
    HashEngine,
    decode_public_key,
    encode_public_key,
    generate_keypair,
    sign,
    verify,
)
from .registry_state import RegistryState


@dataclass
class Curator:
    curator_id: str
    public_key_hex: str
    activation_height: int = 0
    revocation_height: int | None = None
    previous_key_hex: str | None = None

    def is_active_at(self, height: int) -> bool:
        return (
            height >= self.activation_height
            and (self.revocation_height is None or height < self.revocation_height)
        )


class Registry:
    """Curator registry bound to a deterministic chain state."""

    def __init__(self, entries: list[Curator] | None = None):
        self._by_id: dict[str, Curator] = {}
        if entries:
            for c in entries:
                self.register(c)

    def register(self, curator: Curator) -> None:
        if not curator.curator_id:
            raise ValueError("curator_id must not be empty")
        if curator.curator_id in self._by_id:
            raise ValueError(f"curator_id {curator.curator_id!r} already registered")
        if curator.revocation_height is not None and curator.revocation_height < curator.activation_height:
            raise ValueError("revocation_height must be >= activation_height")
        self._by_id[curator.curator_id] = curator

    def add(self, curator_id: str, public_key_hex: str, activation_height: int = 0,
            revocation_height: int | None = None, previous_key_hex: str | None = None) -> None:
        """Convenience method to register a curator from raw fields."""
        self.register(Curator(
            curator_id=curator_id,
            public_key_hex=public_key_hex,
            activation_height=activation_height,
            revocation_height=revocation_height,
            previous_key_hex=previous_key_hex,
        ))

    def get(self, curator_id: str) -> Curator | None:
        return self._by_id.get(curator_id)

    def is_active(self, curator_id: str, height: int) -> bool:
        curator = self.get(curator_id)
        return curator is not None and curator.is_active_at(height)

    def active_keys(self, height: int) -> dict[str, str]:
        return {
            c.curator_id: c.public_key_hex
            for c in self._by_id.values()
            if c.is_active_at(height)
        }

    def apply_registry_transaction(self, tx_body: dict[str, Any], height: int) -> None:
        """Update registry state from a validated registry transaction."""
        action = tx_body["action"]
        curator_id = tx_body["curator_id"]
        public_key_hex = tx_body["public_key_hex"]
        if action == "add":
            self.register(Curator(
                curator_id=curator_id,
                public_key_hex=public_key_hex,
                activation_height=tx_body["activation_height"],
                revocation_height=tx_body.get("revocation_height"),
                previous_key_hex=tx_body.get("previous_key_hex"),
            ))
        elif action == "revoke":
            existing = self.get(curator_id)
            if existing is None:
                raise ValueError(f"cannot revoke unknown curator {curator_id}")
            existing.revocation_height = min(
                existing.revocation_height or height,
                height,
            )
        elif action == "rotate":
            existing = self.get(curator_id)
            if existing is None:
                raise ValueError(f"cannot rotate unknown curator {curator_id}")
            existing.revocation_height = height
            self.register(Curator(
                curator_id=curator_id,
                public_key_hex=public_key_hex,
                activation_height=height,
                revocation_height=tx_body.get("revocation_height"),
                previous_key_hex=existing.public_key_hex,
            ))

    def to_list(self) -> list[dict[str, Any]]:
        return [asdict(c) for c in self._by_id.values()]

    @classmethod
    def from_list(cls, items: list[dict[str, Any]]) -> Registry:
        return cls([Curator(**c) for c in items])


def attestation_message(body_hash: str, curator_id: str, timestamp: int) -> bytes:
    """Canonical message that a curator signs."""
    msg = {
        "network_id": NETWORK_ID,
        "version": 1,
        "body_hash": body_hash,
        "curator_id": curator_id,
        "timestamp": timestamp,
    }
    return HashEngine.hash_object(msg)


def sign_attestation(sk: Ed25519PrivateKey,
                     body_hash: str,
                     curator_id: str,
                     timestamp: int | None = None) -> dict[str, Any]:
    if timestamp is None:
        timestamp = int(time.time())
    msg = attestation_message(body_hash, curator_id, timestamp)
    return {
        "curator_id": curator_id,
        "timestamp": timestamp,
        "signature": sign(sk, msg),
    }


def verify_attestation(registry: Registry,
                       witness: dict[str, Any],
                       body_hash: str,
                       block_height: int) -> bool:
    """Cryptographic and registry validity only. No freshness check."""
    try:
        curator_id = witness["curator_id"]
        signature_hex = witness["signature"]
        timestamp = witness["timestamp"]
        if not isinstance(curator_id, str) or not isinstance(signature_hex, str):
            return False
        if not isinstance(timestamp, int) or isinstance(timestamp, bool):
            return False
        curator = registry.get(curator_id)
        if curator is None:
            return False
        if not curator.is_active_at(block_height):
            return False
        pk = decode_public_key(curator.public_key_hex)
        msg = attestation_message(body_hash, curator_id, timestamp)
        return verify(pk, msg, signature_hex)
    except (ValueError, KeyError, TypeError):
        return False



def attestation_message_v2(body_hash: str, curator_id: str, block_height: int) -> bytes:
    """Canonical message for a historical attestation.

    The block_height is part of the signed domain so a signature cannot be
    moved to a different height without detection.
    """
    msg = {
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "attestation",
        "body_hash": body_hash,
        "curator_id": curator_id,
        "block_height": block_height,
    }
    return HashEngine.hash_object(msg)


def sign_attestation_v2(sk: Ed25519PrivateKey,
                        body_hash: str,
                        curator_id: str,
                        block_height: int) -> dict[str, Any]:
    """Create a v2 historical attestation."""
    msg = attestation_message_v2(body_hash, curator_id, block_height)
    return {
        "curator_id": curator_id,
        "block_height": block_height,
        "signature": sign(sk, msg),
    }


def verify_attestation_v2(state: RegistryState,
                          witness: dict[str, Any],
                          body_hash: str,
                          block_height: int) -> bool:
    """Verify a v2 attestation against the historical registry state.

    The signature is valid only if the claimed key was active for the
    specified curator at block_height.  This intentionally does NOT use the
    current ledger state.
    """
    try:
        curator_id = witness["curator_id"]
        signature_hex = witness["signature"]
        witness_height = witness["block_height"]
        if not isinstance(curator_id, str) or not isinstance(signature_hex, str):
            return False
        if not isinstance(witness_height, int) or isinstance(witness_height, bool):
            return False
        if witness_height != block_height:
            return False
        public_key_hex = witness.get("public_key_hex")
        if not isinstance(public_key_hex, str) or len(public_key_hex) != 64:
            return False
        if not state.key_was_valid_at(curator_id, public_key_hex, block_height):
            return False
        pk = decode_public_key(public_key_hex)
        msg = attestation_message_v2(body_hash, curator_id, block_height)
        return verify(pk, msg, signature_hex)
    except (ValueError, KeyError, TypeError):
        return False


def verify_transaction_witnesses_v2(state: RegistryState,
                                    tx: dict[str, Any],
                                    block_height: int,
                                    min_attestations: int = 1) -> bool:
    """Verify all v2-style witnesses for an archive transaction against historical state.

    Governance transactions carry their own signatures and are validated by the
    registry reducer; this function is for archive/scripture transactions that
    require curator attestations.  V2 witnesses use block_height instead of
    timestamp and are not validated by the legacy schema checker.
    """
    if not isinstance(tx, dict):
        return False
    if not isinstance(tx.get("body"), dict):
        return False
    if not isinstance(tx.get("witnesses"), list):
        return False

    body_hash = HashEngine.hash_object_hex(tx["body"])
    seen_curators: set[str] = set()
    valid = 0
    for witness in tx.get("witnesses", []):
        curator_id = witness.get("curator_id")
        if not isinstance(curator_id, str) or curator_id in seen_curators:
            return False
        seen_curators.add(curator_id)
        if not verify_attestation_v2(state, witness, body_hash, block_height):
            return False
        valid += 1
    return valid >= min_attestations


def is_fresh(witness: dict[str, Any], now: int | None = None,
             max_age_seconds: int = 86400) -> bool:
    """Freshness check for initial submission only."""
    if now is None:
        now = int(time.time())
    try:
        return abs(now - int(witness["timestamp"])) <= max_age_seconds
    except (KeyError, TypeError, ValueError):
        return False


def verify_transaction_witnesses(registry: Registry,
                                 tx: dict[str, Any],
                                 block_height: int,
                                 *,
                                 require_fresh: bool = False,
                                 now: int | None = None,
                                 min_attestations: int = 1) -> bool:
    """Verify all witnesses for a transaction."""
    try:
        validate_transaction(tx)
    except Exception:
        return False

    body_hash = HashEngine.hash_object_hex(tx["body"])
    seen_curators: set[str] = set()
    valid = 0
    for witness in tx["witnesses"]:
        curator_id = witness.get("curator_id")
        if curator_id in seen_curators:
            return False
        seen_curators.add(curator_id)
        if not verify_attestation(registry, witness, body_hash, block_height):
            return False
        if require_fresh and not is_fresh(witness, now=now):
            return False
        valid += 1
    return valid >= min_attestations


class CuratorSigner:
    """Helper to generate keys and sign attestations."""

    def __init__(self, curator_id: str, sk: Ed25519PrivateKey | None = None, pk: Ed25519PublicKey | None = None):
        self.curator_id = curator_id
        if sk is None:
            sk, pk = generate_keypair()
        else:
            if pk is None:
                pk = sk.public_key()
        if sk is None or pk is None:
            raise ValueError("CuratorSigner requires a private key")
        self.sk = sk
        self.pk = pk
        self.public_key_hex = encode_public_key(pk)

    def as_curator(self, activation_height: int = 0, revocation_height: int | None = None) -> Curator:
        return Curator(
            curator_id=self.curator_id,
            public_key_hex=self.public_key_hex,
            activation_height=activation_height,
            revocation_height=revocation_height,
        )

    def sign_attestation(self, network_id: str, version: int, body_hash: str, timestamp: int | None = None) -> dict[str, Any]:
        """Sign an attestation for a given body hash."""
        if timestamp is None:
            timestamp = int(time.time())
        msg = attestation_message(body_hash, self.curator_id, timestamp)
        return {
            "curator_id": self.curator_id,
            "timestamp": timestamp,
            "signature": sign(self.sk, msg),
        }

    def sign_manifest(self, body: dict[str, Any], timestamp: int | None = None) -> dict[str, Any]:
        """Backwards-compatible alias that signs a manifest body."""
        body_hash = HashEngine.hash_object_hex(body)
        return self.sign_attestation(network_id=NETWORK_ID, version=1, body_hash=body_hash, timestamp=timestamp)
