
"""Canonical binary codec for Chain-Breaker primitives.

- Explicit little-endian byte order everywhere
- Exact-length checks; no silent truncation
- Strict UTF-8 decoding
- Minimal, defensively bounded
"""

from __future__ import annotations

import json
import struct
from typing import Dict, Any, Tuple


class CodecError(ValueError):
    """Raised when encoding or decoding fails."""


class BinaryCodec:
    """Binary encoder/decoder for block headers and scripture transactions."""

    ENDIAN = "<"  # little-endian

    TYPE_TX = 0x01
    TYPE_HEADER = 0x02

    HASH_LEN = 32
    ADDR_LEN = 20

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
        if n <= 0xFFFFFFFFFFFFFFFF:
            return b"\xff" + struct.pack(f"{cls.ENDIAN}Q", n)
        raise CodecError("varint too large")

    @classmethod
    def decode_varint(cls, data: bytes, offset: int) -> Tuple[int, int]:
        cls._need(data, offset, 1)
        prefix = data[offset]
        if prefix < 0xFD:
            return prefix, offset + 1
        if prefix == 0xFD:
            cls._need(data, offset + 1, 2)
            return struct.unpack_from(f"{cls.ENDIAN}H", data, offset + 1)[0], offset + 3
        if prefix == 0xFE:
            cls._need(data, offset + 1, 4)
            return struct.unpack_from(f"{cls.ENDIAN}I", data, offset + 1)[0], offset + 5
        if prefix == 0xFF:
            cls._need(data, offset + 1, 8)
            return struct.unpack_from(f"{cls.ENDIAN}Q", data, offset + 1)[0], offset + 9
        raise CodecError(f"invalid varint prefix 0x{prefix:02x}")

    @classmethod
    def encode_bytes(cls, blob: bytes) -> bytes:
        return cls.encode_varint(len(blob)) + blob

    @classmethod
    def decode_bytes(cls, data: bytes, offset: int) -> Tuple[bytes, int]:
        length, offset = cls.decode_varint(data, offset)
        cls._need(data, offset, length)
        return data[offset : offset + length], offset + length

    @classmethod
    def encode_header(cls, header: Dict[str, Any]) -> bytes:
        """Encode BlockHeader as deterministic bytes."""
        try:
            return b"".join([
                struct.pack(f"{cls.ENDIAN}B", cls.TYPE_HEADER),
                struct.pack(f"{cls.ENDIAN}I", int(header["version"])),
                cls.encode_hash(header["prev_hash"]),
                cls.encode_hash(header["merkle_root"]),
                struct.pack(f"{cls.ENDIAN}Q", int(header["timestamp"])),
                struct.pack(f"{cls.ENDIAN}I", int(header["difficulty"])),
                struct.pack(f"{cls.ENDIAN}Q", int(header["nonce"])),
            ])
        except (KeyError, ValueError) as exc:
            raise CodecError(f"invalid header: {exc}") from exc

    @classmethod
    def decode_header(cls, data: bytes) -> Tuple[Dict[str, Any], int]:
        cls._need(data, 0, 1)
        if data[0] != cls.TYPE_HEADER:
            raise CodecError(f"expected header type 0x{cls.TYPE_HEADER:02x}")
        offset = 1
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
        cls._need(data, offset, 4)
        difficulty = struct.unpack_from(f"{cls.ENDIAN}I", data, offset)[0]
        offset += 4
        cls._need(data, offset, 8)
        nonce = struct.unpack_from(f"{cls.ENDIAN}Q", data, offset)[0]
        offset += 8
        return {
            "version": version,
            "prev_hash": prev_hash,
            "merkle_root": merkle_root,
            "timestamp": timestamp,
            "difficulty": difficulty,
            "nonce": nonce,
        }, offset

    @classmethod
    def encode_transaction(cls, tx: Dict[str, Any]) -> bytes:
        """Encode a scripture transaction."""
        tx_type = tx.get("type", "")
        body = tx.get("body", {})
        body_bytes = HashEngine.canonical_json(body)
        witnesses = HashEngine.canonical_json(tx.get("witnesses", []))
        try:
            return b"".join([
                struct.pack(f"{cls.ENDIAN}B", cls.TYPE_TX),
                cls.encode_varint(int(tx["version"])),
                cls.encode_bytes(tx_type.encode("utf-8")),
                cls.encode_bytes(body_bytes),
                cls.encode_bytes(witnesses),
            ])
        except KeyError as exc:
            raise CodecError(f"invalid transaction: {exc}") from exc

    @classmethod
    def decode_transaction(cls, data: bytes) -> Tuple[Dict[str, Any], int]:
        cls._need(data, 0, 1)
        if data[0] != cls.TYPE_TX:
            raise CodecError(f"expected tx type 0x{cls.TYPE_TX:02x}")
        offset = 1
        version, offset = cls.decode_varint(data, offset)
        tx_type_b, offset = cls.decode_bytes(data, offset)
        body_b, offset = cls.decode_bytes(data, offset)
        witnesses_b, offset = cls.decode_bytes(data, offset)
        return {
            "version": version,
            "type": tx_type_b.decode("utf-8"),
            "body": json.loads(body_b.decode("utf-8")),
            "witnesses": json.loads(witnesses_b.decode("utf-8")),
        }, offset
