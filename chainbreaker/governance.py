"""Governance transaction models for curator registry state changes.

This module implements the protocol-v2 registry governance transactions:
    - curator_register
    - curator_rotate
    - curator_revoke

It intentionally does not depend on the current ledger, block header, or CLI.
All operations are deterministic and work on plain data structures.
"""

# CONSENSUS-CRITICAL: module-level consensus-sensitive code (governance.py)
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .crypto import HashEngine

NETWORK_ID = "chainbreaker-scripture-v2"
PROTOCOL_VERSION = 2

GOVERNANCE_SCHEMA_VERSION = 1
MAX_CURATOR_ID_BYTES = 128
MAX_REASON_CODE_BYTES = 64


class GovernanceError(ValueError):
    """Raised when a governance transaction or signature is invalid."""


@dataclass(frozen=True)
class GovernanceSignature:
    """A signature from one genesis governance key."""

    key_index: int
    signature_hex: str

    def to_dict(self) -> dict[str, Any]:
        return {"key_index": self.key_index, "signature": self.signature_hex}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GovernanceSignature:
        if not isinstance(data, dict):
            raise GovernanceError("signature must be a dict")
        if set(data.keys()) != {"key_index", "signature"}:
            raise GovernanceError("signature has wrong keys")
        if not isinstance(data["key_index"], int) or isinstance(data["key_index"], bool):
            raise GovernanceError("key_index must be an integer")
        if data["key_index"] < 0:
            raise GovernanceError("key_index must be non-negative")
        sig = data["signature"]
        if not isinstance(sig, str):
            raise GovernanceError("signature must be a string")
        try:
            sig_bytes = bytes.fromhex(sig)
        except ValueError as exc:
            raise GovernanceError("signature must be hex") from exc
        if len(sig_bytes) != 64:
            raise GovernanceError("signature must be 64 bytes hex")
        return cls(key_index=data["key_index"], signature_hex=sig)


def _require_hex_hash(value: Any, name: str, length: int = 64) -> str:
    if not isinstance(value, str):
        raise GovernanceError(f"{name} must be a string")
    try:
        raw = bytes.fromhex(value)
    except ValueError as exc:
        raise GovernanceError(f"{name} must be hex") from exc
    if len(raw) * 2 != length:
        raise GovernanceError(f"{name} must be {length} hex characters")
    return value.lower()


def _require_curator_id(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise GovernanceError("curator_id must be a non-empty string")
    encoded = value.encode("utf-8")
    if len(encoded) < 1 or len(encoded) > MAX_CURATOR_ID_BYTES:
        raise GovernanceError(f"curator_id must be 1..{MAX_CURATOR_ID_BYTES} UTF-8 bytes")
    return value


def _require_reason_code(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise GovernanceError("reason_code must be a non-empty string")
    encoded = value.encode("utf-8")
    if len(encoded) > MAX_REASON_CODE_BYTES:
        raise GovernanceError(f"reason_code must be <= {MAX_REASON_CODE_BYTES} UTF-8 bytes")
    return value


def _require_height(value: Any, name: str, min_value: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GovernanceError(f"{name} must be an integer")
    if value < min_value:
        raise GovernanceError(f"{name} must be >= {min_value}")
    return value


def _require_optional_hex_hash(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _require_hex_hash(value, name)


def _require_signatures(value: Any) -> list[GovernanceSignature]:
    if not isinstance(value, list):
        raise GovernanceError("governance_signatures must be a list")
    return [GovernanceSignature.from_dict(item) for item in value]


@dataclass(frozen=True)
class CuratorRegisterTx:
    """Governance transaction to register a new curator."""

    curator_id: str
    public_key_hex: str
    activation_height: int
    display_metadata_hash: str | None
    previous_registry_root: str
    governance_signatures: list[GovernanceSignature]
    network_id: str = NETWORK_ID
    schema_version: int = GOVERNANCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "action": "curator_register",
            "curator_id": self.curator_id,
            "public_key_hex": self.public_key_hex,
            "activation_height": self.activation_height,
            "previous_registry_root": self.previous_registry_root,
            "governance_signatures": [s.to_dict() for s in self.governance_signatures],
            "network_id": self.network_id,
            "schema_version": self.schema_version,
        }
        if self.display_metadata_hash is not None:
            result["display_metadata_hash"] = self.display_metadata_hash
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CuratorRegisterTx:
        if not isinstance(data, dict):
            raise GovernanceError("register transaction body must be a dict")
        expected_keys = {
            "action",
            "curator_id",
            "public_key_hex",
            "activation_height",
            "previous_registry_root",
            "governance_signatures",
            "network_id",
            "schema_version",
            "display_metadata_hash",
        }
        actual_keys = set(data.keys())
        if actual_keys - expected_keys:
            raise GovernanceError(f"unexpected keys: {actual_keys - expected_keys}")
        if data.get("action") != "curator_register":
            raise GovernanceError("action must be curator_register")
        if data.get("network_id", NETWORK_ID) != NETWORK_ID:
            raise GovernanceError("wrong network_id")
        if data.get("schema_version", GOVERNANCE_SCHEMA_VERSION) != GOVERNANCE_SCHEMA_VERSION:
            raise GovernanceError("unsupported schema_version")
        return cls(
            curator_id=_require_curator_id(data["curator_id"]),
            public_key_hex=_require_hex_hash(data["public_key_hex"], "public_key_hex", 64),
            activation_height=_require_height(data["activation_height"], "activation_height"),
            display_metadata_hash=_require_optional_hex_hash(data.get("display_metadata_hash"), "display_metadata_hash"),
            previous_registry_root=_require_hex_hash(data["previous_registry_root"], "previous_registry_root", 64),
            governance_signatures=_require_signatures(data["governance_signatures"]),
        )


@dataclass(frozen=True)
class CuratorRotateTx:
    """Governance transaction to rotate a curator's active key."""

    curator_id: str
    public_key_hex: str
    new_public_key_hex: str
    activation_height: int
    display_metadata_hash: str | None
    previous_registry_root: str
    governance_signatures: list[GovernanceSignature]
    curator_signature_hex: str
    network_id: str = NETWORK_ID
    schema_version: int = GOVERNANCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "action": "curator_rotate",
            "curator_id": self.curator_id,
            "public_key_hex": self.public_key_hex,
            "new_public_key_hex": self.new_public_key_hex,
            "activation_height": self.activation_height,
            "previous_registry_root": self.previous_registry_root,
            "governance_signatures": [s.to_dict() for s in self.governance_signatures],
            "curator_signature": self.curator_signature_hex,
            "network_id": self.network_id,
            "schema_version": self.schema_version,
        }
        if self.display_metadata_hash is not None:
            result["display_metadata_hash"] = self.display_metadata_hash
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CuratorRotateTx:
        if not isinstance(data, dict):
            raise GovernanceError("rotate transaction body must be a dict")
        expected_keys = {
            "action",
            "curator_id",
            "public_key_hex",
            "new_public_key_hex",
            "activation_height",
            "previous_registry_root",
            "governance_signatures",
            "curator_signature",
            "network_id",
            "schema_version",
            "display_metadata_hash",
        }
        actual_keys = set(data.keys())
        if actual_keys - expected_keys:
            raise GovernanceError(f"unexpected keys: {actual_keys - expected_keys}")
        if data.get("action") != "curator_rotate":
            raise GovernanceError("action must be curator_rotate")
        if data.get("network_id", NETWORK_ID) != NETWORK_ID:
            raise GovernanceError("wrong network_id")
        if data.get("schema_version", GOVERNANCE_SCHEMA_VERSION) != GOVERNANCE_SCHEMA_VERSION:
            raise GovernanceError("unsupported schema_version")
        return cls(
            curator_id=_require_curator_id(data["curator_id"]),
            public_key_hex=_require_hex_hash(data["public_key_hex"], "public_key_hex", 64),
            new_public_key_hex=_require_hex_hash(data["new_public_key_hex"], "new_public_key_hex", 64),
            activation_height=_require_height(data["activation_height"], "activation_height"),
            display_metadata_hash=_require_optional_hex_hash(data.get("display_metadata_hash"), "display_metadata_hash"),
            previous_registry_root=_require_hex_hash(data["previous_registry_root"], "previous_registry_root", 64),
            governance_signatures=_require_signatures(data["governance_signatures"]),
            curator_signature_hex=_require_hex_hash(data["curator_signature"], "curator_signature", 128),
        )


@dataclass(frozen=True)
class CuratorRevokeTx:
    """Governance transaction to revoke a curator."""

    curator_id: str
    public_key_hex: str
    revocation_height: int
    reason_code: str
    previous_registry_root: str
    governance_signatures: list[GovernanceSignature]
    curator_signature_hex: str
    network_id: str = NETWORK_ID
    schema_version: int = GOVERNANCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": "curator_revoke",
            "curator_id": self.curator_id,
            "public_key_hex": self.public_key_hex,
            "revocation_height": self.revocation_height,
            "reason_code": self.reason_code,
            "previous_registry_root": self.previous_registry_root,
            "governance_signatures": [s.to_dict() for s in self.governance_signatures],
            "curator_signature": self.curator_signature_hex,
            "network_id": self.network_id,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CuratorRevokeTx:
        if not isinstance(data, dict):
            raise GovernanceError("revoke transaction body must be a dict")
        expected_keys = {
            "action",
            "curator_id",
            "public_key_hex",
            "revocation_height",
            "reason_code",
            "previous_registry_root",
            "governance_signatures",
            "curator_signature",
            "network_id",
            "schema_version",
        }
        actual_keys = set(data.keys())
        if actual_keys - expected_keys:
            raise GovernanceError(f"unexpected keys: {actual_keys - expected_keys}")
        if data.get("action") != "curator_revoke":
            raise GovernanceError("action must be curator_revoke")
        if data.get("network_id", NETWORK_ID) != NETWORK_ID:
            raise GovernanceError("wrong network_id")
        if data.get("schema_version", GOVERNANCE_SCHEMA_VERSION) != GOVERNANCE_SCHEMA_VERSION:
            raise GovernanceError("unsupported schema_version")
        return cls(
            curator_id=_require_curator_id(data["curator_id"]),
            public_key_hex=_require_hex_hash(data["public_key_hex"], "public_key_hex", 64),
            revocation_height=_require_height(data["revocation_height"], "revocation_height"),
            reason_code=_require_reason_code(data["reason_code"]),
            previous_registry_root=_require_hex_hash(data["previous_registry_root"], "previous_registry_root", 64),
            governance_signatures=_require_signatures(data["governance_signatures"]),
            curator_signature_hex=_require_hex_hash(data["curator_signature"], "curator_signature", 128),
        )


class GovernanceContext:
    """Static genesis governance configuration."""

    def __init__(self, public_keys_hex: list[str], threshold: int):
        if not 1 <= len(public_keys_hex) <= 16:
            raise GovernanceError("governance key count must be 1..16")
        seen = set()
        for key in public_keys_hex:
            if key in seen:
                raise GovernanceError("duplicate governance key")
            seen.add(key)
            if not isinstance(key, str):
                raise GovernanceError("governance key must be a string")
            try:
                raw = bytes.fromhex(key)
            except ValueError as exc:
                raise GovernanceError("governance key must be hex") from exc
            if len(raw) != 32:
                raise GovernanceError("governance key must be 32 bytes hex")
        if not 1 <= threshold <= len(public_keys_hex):
            raise GovernanceError("threshold must be 1..len(public_keys_hex)")
        self.public_keys_hex = tuple(public_keys_hex)
        self.threshold = threshold

    def verify_governance_signatures(
        self,
        body: dict[str, Any],
        signatures: list[GovernanceSignature],
    ) -> None:
        from .crypto import decode_public_key, verify

        message = HashEngine.hash_object({
            "network_id": NETWORK_ID,
            "version": PROTOCOL_VERSION,
            "type": "registry",
            "body_hash": HashEngine.hash_object_hex(body),
        })
        used_indices: set[int] = set()
        valid = 0
        for sig in signatures:
            if not isinstance(sig.key_index, int) or sig.key_index < 0:
                raise GovernanceError("invalid key_index")
            if sig.key_index >= len(self.public_keys_hex):
                raise GovernanceError("key_index out of range")
            if sig.key_index in used_indices:
                raise GovernanceError("duplicate governance key index")
            used_indices.add(sig.key_index)
            try:
                pk = decode_public_key(self.public_keys_hex[sig.key_index])
                if verify(pk, message, sig.signature_hex):
                    valid += 1
            except (ValueError, TypeError, KeyError):
                # Malformed signature or public key: treat as invalid for this index.
                continue
        if valid < self.threshold:
            raise GovernanceError("insufficient valid governance signatures")


GovernanceTx = CuratorRegisterTx | CuratorRotateTx | CuratorRevokeTx


def governance_message(body_dict: dict[str, Any]) -> bytes:
    """Return the canonical message bytes that governance keys sign.

    The signed message covers the network_id, protocol version, transaction
    type, and the body hash. It intentionally does not cover the witnesses.
    """
    body_hash = HashEngine.hash_object_hex(body_dict)
    msg = {
        "network_id": NETWORK_ID,
        "version": PROTOCOL_VERSION,
        "type": "registry",
        "body_hash": body_hash,
    }
    return HashEngine.hash_object(msg)


def make_governance_signature(
    sk: Any,
    body_dict: dict[str, Any],
    key_index: int,
) -> GovernanceSignature:
    """Create a governance signature for a transaction body dict.

    `sk` may be an Ed25519PrivateKey object or 32 raw bytes.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from .crypto import decode_private_key, sign

    if isinstance(sk, bytes) and len(sk) == 32:
        private_key = decode_private_key(sk.hex())
    elif isinstance(sk, Ed25519PrivateKey):
        private_key = sk
    else:
        raise GovernanceError("invalid private key")
    msg = governance_message(body_dict)
    sig_hex = sign(private_key, msg)
    return GovernanceSignature(key_index=key_index, signature_hex=sig_hex)
