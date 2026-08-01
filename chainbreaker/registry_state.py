"""Deterministic ledger-derived curator registry state.

This module is deliberately isolated from the block header, chain admission,
and CLI. It implements:

  - an immutable registry state representation
  - canonical serialization of the registry state
  - the deterministic registry root (SHA-256 of canonical bytes)
  - a pure reducer that applies governance transactions to produce new state
  - historical lookup helpers that answer questions about key validity at a
    specific block height

All functions are deterministic and have no filesystem, network, wall-clock,
or random dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .crypto import HashEngine
from .governance import (
    GOVERNANCE_SCHEMA_VERSION,
    NETWORK_ID,
    PROTOCOL_VERSION,
    CuratorRegisterTx,
    CuratorRevokeTx,
    CuratorRotateTx,
    GovernanceContext,
    GovernanceTx,
)


class RegistryError(ValueError):
    """Raised when registry state or a state transition is invalid."""


@dataclass(frozen=True)
class CuratorRecord:
    """One curator entry in the registry."""

    curator_id: str
    public_key_hex: str
    activation_height: int
    revocation_height: int | None
    previous_key_hex: str | None
    registration_txid: str
    latest_rotation_txid: str | None

    def is_active_at(self, height: int) -> bool:
        return (
            height >= self.activation_height
            and (self.revocation_height is None or height < self.revocation_height)
        )

    def is_registered(self) -> bool:
        """A record is registered if it has not been replaced by a rotation."""
        return True

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "curator_id": self.curator_id,
            "public_key_hex": self.public_key_hex,
            "activation_height": self.activation_height,
            "revocation_height": self.revocation_height,
            "previous_key_hex": self.previous_key_hex,
            "registration_txid": self.registration_txid,
            "latest_rotation_txid": self.latest_rotation_txid,
        }
        return result


@dataclass(frozen=True)
class RegistryState:
    """Immutable registry state at a particular point in chain history."""

    records: tuple[CuratorRecord, ...]
    governance_version: int = GOVERNANCE_SCHEMA_VERSION
    network_id: str = NETWORK_ID
    governance_keys: tuple[str, ...] = ()
    threshold: int = 0

    def __hash__(self) -> int:
        # tuples are hashable; records are frozen dataclasses
        return hash((self.network_id, self.governance_version, self.records))

    def by_id(self, curator_id: str) -> CuratorRecord | None:
        matches = [r for r in self.records if r.curator_id == curator_id]
        if not matches:
            return None
        # Return the latest record by activation height
        return max(matches, key=lambda r: r.activation_height)

    def is_active(self, curator_id: str, height: int) -> bool:
        record = self.by_id(curator_id)
        return record is not None and record.is_active_at(height)

    def active_key_at(self, curator_id: str, height: int) -> str | None:
        record = self.by_id(curator_id)
        if record is None:
            return None
        if not record.is_active_at(height):
            return None
        return record.public_key_hex

    def key_was_valid_at(self, curator_id: str, public_key_hex: str, height: int) -> bool:
        matches = [r for r in self.records if r.curator_id == curator_id]
        if not matches:
            return False
        for record in matches:
            if record.public_key_hex == public_key_hex and record.is_active_at(height):
                return True
            if (
                record.previous_key_hex == public_key_hex
                and height < record.activation_height
            ):
                # previous key valid before the new key's activation
                return True
        return False

    def to_list(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.records]

    @classmethod
    def empty(cls) -> RegistryState:
        return cls(records=())

    @classmethod
    def from_list(cls, items: list[dict[str, Any]]) -> RegistryState:
        records = []
        for item in items:
            records.append(
                CuratorRecord(
                    curator_id=item["curator_id"],
                    public_key_hex=item["public_key_hex"],
                    activation_height=item["activation_height"],
                    revocation_height=item.get("revocation_height"),
                    previous_key_hex=item.get("previous_key_hex"),
                    registration_txid=item["registration_txid"],
                    latest_rotation_txid=item.get("latest_rotation_txid"),
                )
            )
        return cls(records=tuple(records))

    @classmethod
    def genesis(
        cls,
        governance_keys: list[str],
        threshold: int,
    ) -> RegistryState:
        """Create the genesis registry state.

        The genesis state contains the bootstrap governance key set and
        threshold, with no curators.  Governance keys are sorted
        lexicographically to ensure canonical serialization across independent
        implementations.
        """
        if not isinstance(governance_keys, list) or not governance_keys:
            raise RegistryError("genesis requires at least one governance key")
        if not (1 <= threshold <= len(governance_keys)):
            raise RegistryError(
                f"genesis threshold must satisfy 1 <= threshold <= {len(governance_keys)}"
            )
        for key in governance_keys:
            if len(bytes.fromhex(key)) != 32:
                raise RegistryError(f"governance key must be 32 bytes: {key}")
        sorted_keys = sorted(governance_keys)
        return cls(
            records=(),
            governance_version=GOVERNANCE_SCHEMA_VERSION,
            network_id=NETWORK_ID,
            governance_keys=tuple(sorted_keys),
            threshold=threshold,
        )


# Serialization helpers (used only inside this module)

def _encode_varint(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return bytes([0xFD]) + n.to_bytes(2, "little")
    if n <= 0xFFFFFFFF:
        return bytes([0xFE]) + n.to_bytes(4, "little")
    if n <= 0xFFFFFFFFFFFFFFFF:
        return bytes([0xFF]) + n.to_bytes(8, "little")
    raise RegistryError("varint overflow")


def _encode_bytes(data: bytes) -> bytes:
    return _encode_varint(len(data)) + data


def _encode_str(s: str) -> bytes:
    encoded = s.encode("utf-8")
    return _encode_bytes(encoded)


def serialize_registry_state(state: RegistryState) -> bytes:
    """Return the canonical byte representation of the registry state.

    The output is stable, deterministic, and independent of Python object
    identity or dict ordering. Records are sorted by curator_id UTF-8 byte
    order before serialization.
    """
    sorted_records = sorted(state.records, key=lambda r: r.curator_id.encode("utf-8"))
    parts = []
    # state header
    parts.append(state.governance_version.to_bytes(4, "little"))
    parts.append(_encode_str(state.network_id))
    # governance keys
    parts.append(_encode_varint(len(state.governance_keys)))
    for key_hex in state.governance_keys:
        parts.append(bytes.fromhex(key_hex))
    parts.append(state.threshold.to_bytes(1, "little"))
    # curator records
    parts.append(_encode_varint(len(sorted_records)))
    for record in sorted_records:
        parts.append(_serialize_record(record))
    return b"".join(parts)


def _serialize_record(record: CuratorRecord) -> bytes:
    parts = []
    parts.append(GOVERNANCE_SCHEMA_VERSION.to_bytes(4, "little"))
    parts.append(_encode_str(record.curator_id))
    parts.append(bytes.fromhex(record.public_key_hex))
    parts.append(record.activation_height.to_bytes(8, "little"))
    revocation_value = (
        0xFFFFFFFFFFFFFFFF if record.revocation_height is None else record.revocation_height
    )
    parts.append(revocation_value.to_bytes(8, "little"))
    previous = bytes.fromhex(record.previous_key_hex) if record.previous_key_hex else bytes(32)
    parts.append(previous)
    parts.append(bytes.fromhex(record.registration_txid))
    latest = (
        bytes.fromhex(record.latest_rotation_txid)
        if record.latest_rotation_txid
        else bytes(32)
    )
    parts.append(latest)
    return b"".join(parts)


def registry_root(state: RegistryState) -> str:
    """Return the 64-char hex SHA-256 of the canonical registry state bytes."""
    return HashEngine.hash_single_hex(serialize_registry_state(state))


def _txid_from_body(body: dict[str, Any]) -> str:
    """Return a deterministic transaction ID for a governance body.

    We use the canonical JSON hash of the body as the transaction ID. This is
    stable across processes and does not depend on Python object identity.
    """
    return HashEngine.hash_object_hex(body)


# Governance context


# Reducer

def apply_registry_transaction(
    state: RegistryState,
    tx: GovernanceTx,
    block_height: int,
    txid: str,
    context: GovernanceContext,
) -> RegistryState:
    """Pure deterministic reducer.

    Applies one validated governance transaction to a previous registry state
    and returns a new immutable state. The reducer never mutates the input.
    """
    if isinstance(tx, CuratorRegisterTx):
        return _apply_register(state, tx, block_height, txid, context)
    if isinstance(tx, CuratorRotateTx):
        return _apply_rotate(state, tx, block_height, txid, context)
    if isinstance(tx, CuratorRevokeTx):
        return _apply_revoke(state, tx, block_height, txid, context)
    raise RegistryError("unsupported governance transaction type")


def _require_not_registered(state: RegistryState, curator_id: str, public_key_hex: str) -> None:
    for record in state.records:
        if record.curator_id == curator_id:
            raise RegistryError(f"curator_id {curator_id!r} already registered")
        if record.public_key_hex == public_key_hex:
            raise RegistryError(f"public_key_hex already registered under {record.curator_id!r}")


def _require_public_key_unused(state: RegistryState, public_key_hex: str, exclude_curator_id: str | None = None) -> None:
    """Check that public_key_hex is not already used by another curator."""
    for record in state.records:
        if record.public_key_hex == public_key_hex and record.curator_id != exclude_curator_id:
            raise RegistryError(f"public_key_hex already registered under {record.curator_id!r}")


def _apply_register(
    state: RegistryState,
    tx: CuratorRegisterTx,
    block_height: int,
    txid: str,
    context: GovernanceContext,
) -> RegistryState:

    body = tx.to_dict()
    body_without_witness = {k: v for k, v in body.items() if k != "governance_signatures"}
    context.verify_governance_signatures(body_without_witness, tx.governance_signatures)

    if tx.activation_height <= block_height:
        raise RegistryError("activation_height must be greater than block_height")
    if tx.previous_registry_root != registry_root(state):
        raise RegistryError("previous_registry_root does not match current state")

    _require_not_registered(state, tx.curator_id, tx.public_key_hex)

    new_record = CuratorRecord(
        curator_id=tx.curator_id,
        public_key_hex=tx.public_key_hex,
        activation_height=tx.activation_height,
        revocation_height=None,
        previous_key_hex=None,
        registration_txid=txid,
        latest_rotation_txid=None,
    )
    new_records = tuple(sorted(state.records + (new_record,), key=lambda r: r.curator_id.encode("utf-8")))
    return RegistryState(
        records=new_records,
        governance_version=state.governance_version,
        network_id=state.network_id,
        governance_keys=state.governance_keys,
        threshold=state.threshold,
    )


def _require_active_record(state: RegistryState, curator_id: str, public_key_hex: str) -> CuratorRecord:
    record = state.by_id(curator_id)
    if record is None:
        raise RegistryError(f"unknown curator {curator_id!r}")
    if record.public_key_hex != public_key_hex:
        raise RegistryError("public_key_hex does not match active record")
    return record


def _verify_curator_signature(record: CuratorRecord, body_without_witness: dict[str, Any], signature_hex: str) -> None:
    from .crypto import decode_public_key, verify

    message = HashEngine.hash_object({
        "network_id": NETWORK_ID,
        "version": PROTOCOL_VERSION,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body_without_witness),
    })
    pk = decode_public_key(record.public_key_hex)
    if not verify(pk, message, signature_hex):
        raise RegistryError("invalid curator signature")


def _apply_rotate(
    state: RegistryState,
    tx: CuratorRotateTx,
    block_height: int,
    txid: str,
    context: GovernanceContext,
) -> RegistryState:
    body = tx.to_dict()
    body_without_witness = {k: v for k, v in body.items() if k not in {"governance_signatures", "curator_signature"}}
    context.verify_governance_signatures(body_without_witness, tx.governance_signatures)

    if tx.activation_height <= block_height:
        raise RegistryError("activation_height must be greater than block_height")
    if tx.previous_registry_root != registry_root(state):
        raise RegistryError("previous_registry_root does not match current state")

    old_record = _require_active_record(state, tx.curator_id, tx.public_key_hex)
    _verify_curator_signature(old_record, body_without_witness, tx.curator_signature_hex)

    if tx.new_public_key_hex == old_record.public_key_hex:
        raise RegistryError("new public key must differ from current key")
    _require_public_key_unused(state, tx.new_public_key_hex, exclude_curator_id=tx.curator_id)

    revoked_old = replace(old_record, revocation_height=tx.activation_height, latest_rotation_txid=txid)
    new_record = CuratorRecord(
        curator_id=tx.curator_id,
        public_key_hex=tx.new_public_key_hex,
        activation_height=tx.activation_height,
        revocation_height=None,
        previous_key_hex=old_record.public_key_hex,
        registration_txid=old_record.registration_txid,
        latest_rotation_txid=txid,
    )

    new_records = tuple(
        sorted(
            tuple(r for r in state.records if r.curator_id != tx.curator_id) + (revoked_old, new_record),
            key=lambda r: r.curator_id.encode("utf-8"),
        )
    )
    return RegistryState(records=new_records)


def _apply_revoke(
    state: RegistryState,
    tx: CuratorRevokeTx,
    block_height: int,
    txid: str,
    context: GovernanceContext,
) -> RegistryState:
    body = tx.to_dict()
    body_without_witness = {k: v for k, v in body.items() if k not in {"governance_signatures", "curator_signature"}}
    context.verify_governance_signatures(body_without_witness, tx.governance_signatures)

    if tx.revocation_height <= block_height:
        raise RegistryError("revocation_height must be greater than block_height")
    if tx.previous_registry_root != registry_root(state):
        raise RegistryError("previous_registry_root does not match current state")

    old_record = _require_active_record(state, tx.curator_id, tx.public_key_hex)
    _verify_curator_signature(old_record, body_without_witness, tx.curator_signature_hex)

    if old_record.revocation_height is not None:
        raise RegistryError("curator is already revoked")
    if tx.revocation_height < old_record.activation_height:
        raise RegistryError("revocation_height must be >= activation_height")

    revoked = replace(old_record, revocation_height=tx.revocation_height, latest_rotation_txid=txid)
    new_records = tuple(
        sorted(
            tuple(r for r in state.records if r.curator_id != tx.curator_id) + (revoked,),
            key=lambda r: r.curator_id.encode("utf-8"),
        )
    )
    return RegistryState(records=new_records)
