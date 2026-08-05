
"""Canonical binary codec and transaction validation.

- Explicit little-endian byte order everywhere
- Exact-length checks; no silent truncation
- Strict UTF-8 decoding
- Transaction schema validation
"""

from __future__ import annotations

import json
import re
import struct
from typing import Any

from .crypto import HashEngine


class CodecError(ValueError):
    """Raised when encoding or decoding fails."""


class SchemaError(ValueError):
    """Raised when a transaction body does not match its schema."""


class BinaryCodec:
    """Binary encoder/decoder for block headers and transactions."""

    ENDIAN = "<"  # little-endian

    TYPE_TX = 0x01
    TYPE_HEADER = 0x02

    HASH_LEN = 32
    ADDR_LEN = 20
    MAX_VARINT = 0xFFFFFFFFFFFFFFFF
    MAX_TX_TYPE_LEN = 64
    MAX_BODY_LEN = 1024 * 1024  # 1 MiB
    MAX_WITNESSES_LEN = 1024 * 1024

    @classmethod
    def _need(cls, data: bytes, offset: int, length: int) -> None:
        if offset < 0 or length < 0 or offset + length > len(data):
            raise CodecError(
                f"need {length} bytes at offset {offset}, have {len(data)}"
            )

    @classmethod
    def encode_hash(cls, hash_hex: str) -> bytes:
        raw = bytes.fromhex(hash_hex)
        if len(raw) != cls.HASH_LEN:
            raise CodecError(f"hash must be {cls.HASH_LEN} bytes, got {len(raw)}")
        return raw

    @classmethod
    def decode_hash(cls, data: bytes) -> str:
        if len(data) != cls.HASH_LEN:
            raise CodecError(f"hash must be {cls.HASH_LEN} bytes, got {len(data)}")
        return data.hex()

    @classmethod
    def encode_address(cls, addr: str) -> bytes:
        if addr.startswith("CB"):
            addr = addr[2:]
        raw = bytes.fromhex(addr)
        if len(raw) != cls.ADDR_LEN:
            raise CodecError(f"address must be {cls.ADDR_LEN} bytes, got {len(raw)}")
        return raw

    @classmethod
    def decode_address(cls, data: bytes) -> str:
        if len(data) != cls.ADDR_LEN:
            raise CodecError(f"address must be {cls.ADDR_LEN} bytes, got {len(data)}")
        return "CB" + data.hex()

    @classmethod
    def encode_varint(cls, n: int) -> bytes:
        if n < 0:
            raise CodecError("varint cannot be negative")
        if n < 0xFD:
            return struct.pack(f"{cls.ENDIAN}B", n)
        if n <= 0xFFFF:
            return b"\xfd" + struct.pack(f"{cls.ENDIAN}H", n)
        if n <= 0xFFFFFFFF:
            return b"\xfe" + struct.pack(f"{cls.ENDIAN}I", n)
        if n <= cls.MAX_VARINT:
            return b"\xff" + struct.pack(f"{cls.ENDIAN}Q", n)
        raise CodecError("varint too large")

    @classmethod
    def _canonical_length(cls, n: int) -> int:
        if n < 0xFD:
            return 1
        if n <= 0xFFFF:
            return 3
        if n <= 0xFFFFFFFF:
            return 5
        return 9

    @classmethod
    def decode_varint(cls, data: bytes, offset: int) -> tuple[int, int]:
        cls._need(data, offset, 1)
        prefix = data[offset]
        if prefix < 0xFD:
            return prefix, offset + 1
        if prefix == 0xFD:
            cls._need(data, offset + 1, 2)
            n = struct.unpack_from(f"{cls.ENDIAN}H", data, offset + 1)[0]
            if cls._canonical_length(n) != 3:
                raise CodecError("noncanonical varint encoding")
            return n, offset + 3
        if prefix == 0xFE:
            cls._need(data, offset + 1, 4)
            n = struct.unpack_from(f"{cls.ENDIAN}I", data, offset + 1)[0]
            if cls._canonical_length(n) != 5:
                raise CodecError("noncanonical varint encoding")
            return n, offset + 5
        if prefix == 0xFF:
            cls._need(data, offset + 1, 8)
            n = struct.unpack_from(f"{cls.ENDIAN}Q", data, offset + 1)[0]
            if cls._canonical_length(n) != 9:
                raise CodecError("noncanonical varint encoding")
            return n, offset + 9
        raise CodecError(f"invalid varint prefix 0x{prefix:02x}")

    @classmethod
    def encode_bytes(cls, blob: bytes) -> bytes:
        return cls.encode_varint(len(blob)) + blob

    @classmethod
    def decode_bytes(cls, data: bytes, offset: int) -> tuple[bytes, int]:
        length, offset = cls.decode_varint(data, offset)
        cls._need(data, offset, length)
        return data[offset : offset + length], offset + length

    @classmethod
    def decode_string(cls, data: bytes, offset: int) -> tuple[str, int]:
        raw, offset = cls.decode_bytes(data, offset)
        try:
            return raw.decode("utf-8"), offset
        except UnicodeDecodeError as exc:
            raise CodecError(f"invalid utf-8: {exc}") from exc

    @classmethod
    def encode_header(cls, header: dict[str, Any]) -> bytes:
        """Encode BlockHeader as deterministic bytes."""
        try:
            return b"".join([
                struct.pack(f"{cls.ENDIAN}B", cls.TYPE_HEADER),
                struct.pack(f"{cls.ENDIAN}I", int(header["version"])),
                cls.encode_hash(header["prev_hash"]),
                cls.encode_hash(header["merkle_root"]),
                struct.pack(f"{cls.ENDIAN}Q", int(header["timestamp"])),
                cls.encode_hash(header["target"]),
                struct.pack(f"{cls.ENDIAN}Q", int(header["nonce"])),
            ])
        except (KeyError, ValueError) as exc:
            raise CodecError(f"invalid header: {exc}") from exc

    @classmethod
    def decode_header(cls, data: bytes, offset: int = 0) -> tuple[dict[str, Any], int]:
        cls._need(data, offset, 1)
        if data[offset] != cls.TYPE_HEADER:
            raise CodecError(f"expected header type 0x{cls.TYPE_HEADER:02x}")
        offset = offset + 1
        cls._need(data, offset, 4)
        version = struct.unpack_from(f"{cls.ENDIAN}I", data, offset)[0]
        offset += 4
        cls._need(data, offset, cls.HASH_LEN)
        prev_hash = cls.decode_hash(data[offset : offset + cls.HASH_LEN])
        offset += cls.HASH_LEN
        cls._need(data, offset, cls.HASH_LEN)
        merkle_root = cls.decode_hash(data[offset : offset + cls.HASH_LEN])
        offset += cls.HASH_LEN
        cls._need(data, offset, 8)
        timestamp = struct.unpack_from(f"{cls.ENDIAN}Q", data, offset)[0]
        offset += 8
        cls._need(data, offset, cls.HASH_LEN)
        target = cls.decode_hash(data[offset : offset + cls.HASH_LEN])
        offset += cls.HASH_LEN
        cls._need(data, offset, 8)
        nonce = struct.unpack_from(f"{cls.ENDIAN}Q", data, offset)[0]
        offset += 8
        return {
            "version": version,
            "prev_hash": prev_hash,
            "merkle_root": merkle_root,
            "timestamp": timestamp,
            "target": target,
            "nonce": nonce,
        }, offset

    @classmethod
    def encode_header_v2(cls, header: dict[str, Any]) -> bytes:
        """Encode v2 BlockHeader as deterministic 149 bytes.

        Field layout:
            type marker     1 byte   (0x02)
            version         4 bytes  uint32 LE
            prev_hash       32 bytes
            merkle_root     32 bytes
            registry_root   32 bytes
            timestamp       8 bytes  uint64 LE
            target          32 bytes
            nonce           8 bytes  uint64 LE
        """
        try:
            return b"".join([
                struct.pack(f"{cls.ENDIAN}B", cls.TYPE_HEADER),
                struct.pack(f"{cls.ENDIAN}I", int(header["version"])),
                cls.encode_hash(header["prev_hash"]),
                cls.encode_hash(header["merkle_root"]),
                cls.encode_hash(header["registry_root"]),
                struct.pack(f"{cls.ENDIAN}Q", int(header["timestamp"])),
                cls.encode_hash(header["target"]),
                struct.pack(f"{cls.ENDIAN}Q", int(header["nonce"])),
            ])
        except (KeyError, ValueError) as exc:
            raise CodecError(f"invalid header: {exc}") from exc

    @classmethod
    def decode_header_v2(cls, data: bytes, offset: int = 0,
                         *, strict: bool = False) -> tuple[dict[str, Any], int]:
        """Decode v2 BlockHeader.

        When ``strict=True`` the input must be exactly 149 bytes and the
        returned offset must equal ``len(data)``.  This mode is required for
        canonical header validation.  The default ``strict=False`` tolerates
        trailing bytes for stream parsing.
        """
        if strict:
            if offset != 0:
                raise CodecError("strict mode requires offset=0")
            if len(data) != 149:
                raise CodecError(f"v2 header must be exactly 149 bytes, got {len(data)}")
        cls._need(data, offset, 1)
        if data[offset] != cls.TYPE_HEADER:
            raise CodecError(f"expected header type 0x{cls.TYPE_HEADER:02x}")
        offset = offset + 1

        cls._need(data, offset, 4)
        version = struct.unpack_from(f"{cls.ENDIAN}I", data, offset)[0]
        offset += 4

        cls._need(data, offset, cls.HASH_LEN)
        prev_hash = cls.decode_hash(data[offset : offset + cls.HASH_LEN])
        offset += cls.HASH_LEN

        cls._need(data, offset, cls.HASH_LEN)
        merkle_root = cls.decode_hash(data[offset : offset + cls.HASH_LEN])
        offset += cls.HASH_LEN

        cls._need(data, offset, cls.HASH_LEN)
        registry_root = cls.decode_hash(data[offset : offset + cls.HASH_LEN])
        offset += cls.HASH_LEN

        cls._need(data, offset, 8)
        timestamp = struct.unpack_from(f"{cls.ENDIAN}Q", data, offset)[0]
        offset += 8

        cls._need(data, offset, cls.HASH_LEN)
        target = cls.decode_hash(data[offset : offset + cls.HASH_LEN])
        offset += cls.HASH_LEN

        cls._need(data, offset, 8)
        nonce = struct.unpack_from(f"{cls.ENDIAN}Q", data, offset)[0]
        offset += 8

        if strict and offset != len(data):
            raise CodecError(f"strict mode consumed {offset} bytes but data length is {len(data)}")
        return {
            "version": version,
            "prev_hash": prev_hash,
            "merkle_root": merkle_root,
            "registry_root": registry_root,
            "timestamp": timestamp,
            "target": target,
            "nonce": nonce,
        }, offset

    @classmethod
    def encode_transaction(cls, tx: dict[str, Any]) -> bytes:
        """Encode a transaction."""
        tx_type = tx.get("type", "")
        if not isinstance(tx_type, str) or len(tx_type.encode("utf-8")) > cls.MAX_TX_TYPE_LEN:
            raise CodecError("invalid transaction type")
        body = HashEngine.canonical_json(tx.get("body", {}))
        if len(body) > cls.MAX_BODY_LEN:
            raise CodecError("transaction body too large")
        witnesses = HashEngine.canonical_json(tx.get("witnesses", []))
        if len(witnesses) > cls.MAX_WITNESSES_LEN:
            raise CodecError("witnesses too large")
        return b"".join([
            struct.pack(f"{cls.ENDIAN}B", cls.TYPE_TX),
            cls.encode_varint(int(tx["version"])),
            cls.encode_bytes(tx_type.encode("utf-8")),
            cls.encode_bytes(body),
            cls.encode_bytes(witnesses),
        ])

    @classmethod
    def decode_transaction(cls, data: bytes, offset: int = 0) -> tuple[dict[str, Any], int]:
        cls._need(data, offset, 1)
        if data[offset] != cls.TYPE_TX:
            raise CodecError(f"expected tx type 0x{cls.TYPE_TX:02x}")
        offset = offset + 1
        version, offset = cls.decode_varint(data, offset)
        tx_type_b, offset = cls.decode_string(data, offset)
        body_b, offset = cls.decode_bytes(data, offset)
        witnesses_b, offset = cls.decode_bytes(data, offset)
        try:
            body_obj = json.loads(body_b.decode("utf-8"))
            witnesses_obj = json.loads(witnesses_b.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CodecError(f"invalid transaction payload: {exc}") from exc
        return {
            "version": version,
            "type": tx_type_b,
            "body": body_obj,
            "witnesses": witnesses_obj,
        }, offset


HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(HASH_RE.match(value))


def _require_string(value: Any, nullable: bool = False) -> bool:
    if value is None and nullable:
        return True
    return isinstance(value, str) and len(value.encode("utf-8")) <= 65535


def _require_int(value: Any, min_value: int | None = None, max_value: int | None = None) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    if min_value is not None and value < min_value:
        return False
    return not (max_value is not None and value > max_value)


def validate_scripture_body(body: dict[str, Any]) -> None:
    """Validate a scripture/archive manifest body. Raises SchemaError on failure."""
    required = {
        "schema", "content_hash", "byte_length", "media_type", "title",
        "language", "source", "source_uri", "acquisition_date", "license",
        "parent_hash", "metadata_hash", "notes_hash",
    }
    # Protocol v2 manifests may also carry network_id and schema_version.
    allowed = required | {"network_id", "schema_version"}
    if set(body.keys()) - allowed:
        raise SchemaError("scripture body has disallowed keys")
    if not required.issubset(body.keys()):
        raise SchemaError("scripture body is missing required keys")

    if body["schema"] != "chainbreaker-manifest-v1":
        raise SchemaError("unsupported manifest schema")

    if body["schema"] != "chainbreaker-manifest-v1":
        raise SchemaError("unsupported manifest schema")

    if not _is_hash(body["content_hash"]):
        raise SchemaError("content_hash must be a 64-char hex SHA-256")
    if not _is_hash(body["metadata_hash"]):
        raise SchemaError("metadata_hash must be a 64-char hex SHA-256")
    if body["parent_hash"] is not None and not _is_hash(body["parent_hash"]):
        raise SchemaError("parent_hash must be null or a 64-char hex SHA-256")
    if body["notes_hash"] is not None and not _is_hash(body["notes_hash"]):
        raise SchemaError("notes_hash must be null or a 64-char hex SHA-256")

    if not _require_int(body["byte_length"], min_value=1):
        raise SchemaError("byte_length must be a positive integer")

    for key in ("media_type", "title", "language", "source", "source_uri", "license"):
        if not _require_string(body[key], nullable=True):
            raise SchemaError(f"{key} must be a string or null")

    if body["acquisition_date"] is not None and not _require_int(body["acquisition_date"]):
        raise SchemaError("acquisition_date must be an integer Unix timestamp or null")


def validate_genesis_body(body: dict[str, Any]) -> None:
    required = {"network_id", "message", "timestamp"}
    if set(body.keys()) != required:
        raise SchemaError("genesis body has incorrect keys")
    if not isinstance(body["network_id"], str):
        raise SchemaError("network_id must be a string")
    if not isinstance(body["message"], str):
        raise SchemaError("message must be a string")
    if not _require_int(body["timestamp"]):
        raise SchemaError("timestamp must be an integer")


def validate_transaction(tx: dict[str, Any]) -> None:
    """Validate top-level transaction structure and body schema."""
    if not isinstance(tx, dict):
        raise SchemaError("transaction must be a dict")
    if set(tx.keys()) != {"version", "type", "body", "witnesses"}:
        raise SchemaError("transaction has incorrect top-level keys")

    if not _require_int(tx["version"], min_value=1, max_value=1):
        raise SchemaError("unsupported transaction version")

    tx_type = tx["type"]
    body = tx["body"]
    witnesses = tx["witnesses"]

    if tx_type not in {"genesis", "scripture", "registry"}:
        raise SchemaError(f"unsupported transaction type: {tx_type}")

    if tx_type == "genesis":
        validate_genesis_body(body)
    elif tx_type == "scripture":
        validate_scripture_body(body)
    elif tx_type == "registry":
        validate_registry_body(body)

    if not isinstance(witnesses, list):
        raise SchemaError("witnesses must be a list")
    for w in witnesses:
        if not isinstance(w, dict):
            raise SchemaError("witness must be a dict")
        if set(w.keys()) != {"curator_id", "timestamp", "signature"}:
            raise SchemaError("witness has incorrect keys")
        if not isinstance(w["curator_id"], str):
            raise SchemaError("curator_id must be a string")
        if not _require_int(w["timestamp"]):
            raise SchemaError("witness timestamp must be an integer")
        if not isinstance(w["signature"], str):
            raise SchemaError("signature must be a string")


def validate_registry_body(body: dict[str, Any]) -> None:
    required = {
        "action", "curator_id", "public_key_hex", "activation_height",
        "revocation_height", "previous_key_hex",
    }
    if set(body.keys()) != required:
        raise SchemaError("registry body has incorrect keys")

    if body["action"] not in {"add", "revoke", "rotate"}:
        raise SchemaError("registry action must be add, revoke, or rotate")

    if not isinstance(body["curator_id"], str) or not body["curator_id"]:
        raise SchemaError("curator_id must be a non-empty string")

    if not _is_hash(body["public_key_hex"]):
        raise SchemaError("public_key_hex must be a 64-char hex Ed25519 public key")

    if not _require_int(body["activation_height"], min_value=0):
        raise SchemaError("activation_height must be a non-negative integer")

    if body["revocation_height"] is not None and not _require_int(
        body["revocation_height"], min_value=body["activation_height"]
    ):
        raise SchemaError("revocation_height must be null or >= activation_height")

    if body["previous_key_hex"] is not None and not _is_hash(body["previous_key_hex"]):
        raise SchemaError("previous_key_hex must be null or a 64-char hex public key")


# Top-level convenience aliases used by tests and CLI
def encode_transaction(tx: dict[str, Any]) -> bytes:
    return BinaryCodec.encode_transaction(tx)


def decode_transaction(data: bytes, offset: int = 0) -> tuple[dict[str, Any], int]:
    return BinaryCodec.decode_transaction(data, offset)
