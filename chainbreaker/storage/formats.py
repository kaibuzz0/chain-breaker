"""Storage format encoders/decoders.

All functions operate on bytes and enforce exact-length/framing rules. They do
not perform consensus validation.
"""

from __future__ import annotations

import json
import struct
from typing import Any

from chainbreaker.block import BlockHeaderV2, BlockV2
from chainbreaker.codec import BinaryCodec
from chainbreaker.crypto import HashEngine

# Block record v1 framing
BLOCK_MAGIC = b"CBB2"
BLOCK_VERSION = 2
HEADER_LEN = 149
RESERVED_BYTE = b"\x00"
BLOCK_TRAILING = b"\x00\x00\x00\x00"

# Journal record framing
JOURNAL_MAGIC = b"CBJR"

JOURNAL_BEGIN = 0x01
JOURNAL_HEADER_STAGED = 0x02
JOURNAL_BLOCK_STAGED = 0x03
JOURNAL_REGISTRY_STAGED = 0x04
JOURNAL_INDEX_STAGED = 0x05
JOURNAL_ARCHIVE_REF = 0x06
JOURNAL_COMMIT = 0x10
JOURNAL_HEAD_UPDATED = 0x11
JOURNAL_ABORT = 0xFF

# Maximum record sizes
MAX_TX_COUNT = 10_000
MAX_BODY_LEN = 64 * 1024 * 1024  # 64 MiB
MAX_JOURNAL_PAYLOAD = 64 * 1024 * 1024


def encode_block_record(block: BlockV2) -> bytes:
    """Encode a BlockV2 into the Storage Format V1 record."""
    header_bytes = BinaryCodec.encode_header_v2(block.header.to_dict())
    if len(header_bytes) != HEADER_LEN:
        raise ValueError(f"header length {len(header_bytes)} != {HEADER_LEN}")

    body_bytes = json.dumps(
        block.transactions,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    tx_count = len(block.transactions)
    if tx_count > MAX_TX_COUNT:
        raise ValueError(f"tx_count {tx_count} exceeds maximum {MAX_TX_COUNT}")
    body_len = len(body_bytes)
    if body_len > MAX_BODY_LEN:
        raise ValueError(f"body_len {body_len} exceeds maximum {MAX_BODY_LEN}")

    body_prefix = struct.pack("<QI", body_len, tx_count)
    body_checksum = HashEngine.double_sha256(body_prefix + body_bytes)

    parts = [
        BLOCK_MAGIC,
        struct.pack("<I", BLOCK_VERSION),
        struct.pack("<I", HEADER_LEN),
        header_bytes,
        RESERVED_BYTE,
        body_prefix,
        body_bytes,
        body_checksum,
        BLOCK_TRAILING,
    ]
    return b"".join(parts)


def decode_block_record(data: bytes) -> BlockV2:
    """Decode and return a BlockV2 from a Storage Format V1 record."""
    min_len = 4 + 4 + 4 + HEADER_LEN + 1 + 8 + 4 + 32 + 4
    if len(data) < min_len:
        raise ValueError("block record too short")

    offset = 0
    magic = data[offset : offset + 4]
    offset += 4
    if magic != BLOCK_MAGIC:
        raise ValueError(f"bad block magic {magic!r}")

    version = struct.unpack("<I", data[offset : offset + 4])[0]
    offset += 4
    if version != BLOCK_VERSION:
        raise ValueError(f"unsupported block version {version}")

    header_len = struct.unpack("<I", data[offset : offset + 4])[0]
    offset += 4
    if header_len != HEADER_LEN:
        raise ValueError(f"unexpected header_len {header_len}")

    header_bytes = data[offset : offset + HEADER_LEN]
    offset += HEADER_LEN

    reserved = data[offset : offset + 1]
    offset += 1
    if reserved != RESERVED_BYTE:
        raise ValueError(f"unexpected reserved byte {reserved!r}")

    body_len, tx_count = struct.unpack("<QI", data[offset : offset + 12])
    offset += 12
    if body_len > MAX_BODY_LEN:
        raise ValueError(f"body_len {body_len} exceeds maximum")
    if tx_count > MAX_TX_COUNT:
        raise ValueError(f"tx_count {tx_count} exceeds maximum")

    expected_total = min_len + body_len
    if len(data) != expected_total:
        raise ValueError(
            f"block record size mismatch: got {len(data)}, expected {expected_total}"
        )

    body_bytes = data[offset : offset + body_len]
    offset += body_len

    stored_checksum = data[offset : offset + 32]
    offset += 32
    computed_checksum = HashEngine.double_sha256(
        struct.pack("<QI", body_len, tx_count) + body_bytes
    )
    if stored_checksum != computed_checksum:
        raise ValueError("block body checksum mismatch")

    trailing = data[offset : offset + 4]
    offset += 4
    if trailing != BLOCK_TRAILING:
        raise ValueError(f"unexpected trailing bytes {trailing!r}")

    header_dict = BinaryCodec.decode_header_v2(header_bytes)[0]
    transactions = json.loads(body_bytes.decode("utf-8"))
    if not isinstance(transactions, list):
        raise ValueError("transactions must be a JSON array")
    if len(transactions) != tx_count:
        raise ValueError(
            f"transaction count mismatch: header says {tx_count}, JSON has {len(transactions)}"
        )
    return BlockV2(header=BlockHeaderV2.from_dict(header_dict), transactions=transactions)


def encode_head(height: int, block_hash: str, network_id: str, genesis_hash: str, format_version: int = 1) -> bytes:
    """Encode HEAD as atomic pointer text."""
    if len(block_hash) != 64:
        raise ValueError("block_hash must be 64 hex chars")
    if len(genesis_hash) != 64:
        raise ValueError("genesis_hash must be 64 hex chars")
    line = f"{height:020d}:{block_hash}:{network_id}:{genesis_hash}:{format_version}\n"
    return line.encode("utf-8")


def decode_head(data: bytes) -> dict[str, Any]:
    """Decode HEAD and return a dict."""
    try:
        text = data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("HEAD is not valid UTF-8") from exc
    parts = text.split(":")
    if len(parts) != 5:
        raise ValueError(f"HEAD has {len(parts)} fields, expected 5")
    try:
        height = int(parts[0])
    except ValueError as exc:
        raise ValueError("HEAD height is not an integer") from exc
    block_hash = parts[1]
    network_id = parts[2]
    genesis_hash = parts[3]
    try:
        format_version = int(parts[4])
    except ValueError as exc:
        raise ValueError("HEAD format_version is not an integer") from exc
    if len(block_hash) != 64 or any(c not in "0123456789abcdef" for c in block_hash):
        raise ValueError("HEAD block_hash is not 64 lowercase hex chars")
    if len(genesis_hash) != 64 or any(c not in "0123456789abcdef" for c in genesis_hash):
        raise ValueError("HEAD genesis_hash is not 64 lowercase hex chars")
    return {
        "height": height,
        "block_hash": block_hash,
        "network_id": network_id,
        "genesis_hash": genesis_hash,
        "format_version": format_version,
    }


def encode_journal_record(
    record_type: int,
    seq: int,
    height: int,
    payload: bytes = b"",
) -> bytes:
    """Encode a journal record."""
    if len(payload) > MAX_JOURNAL_PAYLOAD:
        raise ValueError(f"payload length {len(payload)} exceeds maximum")
    header_bytes = struct.pack("<4sBQQI", JOURNAL_MAGIC, record_type, seq, height, len(payload))
    checksum = HashEngine.double_sha256(header_bytes[4:] + payload)
    return header_bytes + payload + checksum


def decode_journal_record(data: bytes, offset: int = 0) -> tuple[dict[str, Any], int]:
    """Decode one journal record starting at offset."""
    if offset + 25 > len(data):
        raise ValueError("journal record truncated (header)")

    magic = data[offset : offset + 4]
    if magic != JOURNAL_MAGIC:
        raise ValueError(f"bad journal magic {magic!r}")

    record_type = data[offset + 4]
    seq, height, payload_len = struct.unpack(
        "<QQI", data[offset + 5 : offset + 25]
    )
    if payload_len > MAX_JOURNAL_PAYLOAD:
        raise ValueError(f"payload_len {payload_len} exceeds maximum")

    record_end = offset + 25 + payload_len + 32
    if record_end > len(data):
        raise ValueError("journal record truncated (payload/checksum)")

    payload = data[offset + 25 : offset + 25 + payload_len]
    stored_checksum = data[offset + 25 + payload_len : record_end]
    computed_checksum = HashEngine.double_sha256(
        data[offset + 4 : offset + 25] + payload
    )
    if stored_checksum != computed_checksum:
        raise ValueError("journal record checksum mismatch")

    return {
        "type": record_type,
        "seq": seq,
        "height": height,
        "payload": payload,
    }, record_end
