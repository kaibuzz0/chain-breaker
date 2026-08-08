"""Typed network message payloads.

This module defines dataclasses for each V1 message type and provides
serialization/deserialization functions. It does not implement behavior:
parsing and validation only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .codec import decode_payload, encode_payload
from .constants import (
    ARCHIVE,
    BLOCK,
    GET_ARCHIVE,
    GET_BLOCK,
    GET_DATA,
    GET_HEADERS,
    HEADERS,
    HELLO,
    HELLO_ACK,
    INVENTORY,
    MAX_BLOCKS_RESPONSE,
    MAX_HEADERS_RESPONSE,
    MAX_INVENTORY_ENTRIES,
    MAX_LOCATOR_SIZE,
    PING,
    PONG,
    REJECT,
)
from .errors import NetworkValidationError
from .validation import validate_hex_hash, validate_nonnegative_int


@dataclass(frozen=True, slots=True)
class HelloMessage:
    protocol_version: int
    network_id: str
    genesis_hash: str
    best_height: int
    best_chain_work: str
    feature_bits: list[str]
    node_limits: dict[str, int]

    def to_payload(self) -> bytes:
        return encode_payload({
            "protocol_version": self.protocol_version,
            "network_id": self.network_id,
            "genesis_hash": self.genesis_hash,
            "best_height": self.best_height,
            "best_chain_work": self.best_chain_work,
            "feature_bits": sorted(self.feature_bits),
            "node_limits": dict(sorted(self.node_limits.items())),
        })

    @classmethod
    def from_payload(cls, payload: bytes) -> HelloMessage:
        obj = decode_payload(payload)
        for key in ("protocol_version", "network_id", "genesis_hash", "best_height", "best_chain_work"):
            if key not in obj:
                raise NetworkValidationError(f"missing field: {key}")
        validate_hex_hash(obj["genesis_hash"])
        validate_hex_hash(obj["best_chain_work"])
        validate_nonnegative_int(obj["best_height"])
        return cls(
            protocol_version=int(obj["protocol_version"]),
            network_id=str(obj["network_id"]),
            genesis_hash=str(obj["genesis_hash"]),
            best_height=int(obj["best_height"]),
            best_chain_work=str(obj["best_chain_work"]),
            feature_bits=[str(b) for b in obj.get("feature_bits", [])],
            node_limits={str(k): int(v) for k, v in obj.get("node_limits", {}).items()},
        )


@dataclass(frozen=True, slots=True)
class HelloAckMessage:
    protocol_version: int
    network_id: str
    genesis_hash: str
    best_height: int
    best_chain_work: str
    feature_bits: list[str]
    node_limits: dict[str, int]
    handshake_complete: bool = True

    def to_payload(self) -> bytes:
        return encode_payload({
            "protocol_version": self.protocol_version,
            "network_id": self.network_id,
            "genesis_hash": self.genesis_hash,
            "best_height": self.best_height,
            "best_chain_work": self.best_chain_work,
            "feature_bits": sorted(self.feature_bits),
            "node_limits": dict(sorted(self.node_limits.items())),
            "handshake_complete": self.handshake_complete,
        })

    @classmethod
    def from_payload(cls, payload: bytes) -> HelloAckMessage:
        obj = decode_payload(payload)
        for key in ("protocol_version", "network_id", "genesis_hash", "best_height", "best_chain_work"):
            if key not in obj:
                raise NetworkValidationError(f"missing field: {key}")
        validate_hex_hash(obj["genesis_hash"])
        validate_hex_hash(obj["best_chain_work"])
        validate_nonnegative_int(obj["best_height"])
        return cls(
            protocol_version=int(obj["protocol_version"]),
            network_id=str(obj["network_id"]),
            genesis_hash=str(obj["genesis_hash"]),
            best_height=int(obj["best_height"]),
            best_chain_work=str(obj["best_chain_work"]),
            feature_bits=[str(b) for b in obj.get("feature_bits", [])],
            node_limits={str(k): int(v) for k, v in obj.get("node_limits", {}).items()},
            handshake_complete=bool(obj.get("handshake_complete", False)),
        )


@dataclass(frozen=True, slots=True)
class PingMessage:
    nonce: int

    def to_payload(self) -> bytes:
        return encode_payload({"nonce": self.nonce})

    @classmethod
    def from_payload(cls, payload: bytes) -> PingMessage:
        obj = decode_payload(payload)
        if "nonce" not in obj:
            raise NetworkValidationError("missing field: nonce")
        validate_nonnegative_int(obj["nonce"])
        return cls(nonce=int(obj["nonce"]))


@dataclass(frozen=True, slots=True)
class PongMessage:
    nonce: int

    def to_payload(self) -> bytes:
        return encode_payload({"nonce": self.nonce})

    @classmethod
    def from_payload(cls, payload: bytes) -> PongMessage:
        obj = decode_payload(payload)
        if "nonce" not in obj:
            raise NetworkValidationError("missing field: nonce")
        validate_nonnegative_int(obj["nonce"])
        return cls(nonce=int(obj["nonce"]))


@dataclass(frozen=True, slots=True)
class GetHeadersMessage:
    start_hashes: list[str]
    stop_hash: str | None
    max_count: int

    def to_payload(self) -> bytes:
        return encode_payload({
            "start_hashes": self.start_hashes,
            "stop_hash": self.stop_hash,
            "max_count": self.max_count,
        })

    @classmethod
    def from_payload(cls, payload: bytes) -> GetHeadersMessage:
        obj = decode_payload(payload)
        start_hashes = obj.get("start_hashes", [])
        if not isinstance(start_hashes, list) or len(start_hashes) > MAX_LOCATOR_SIZE:
            raise NetworkValidationError(f"invalid start_hashes length: {len(start_hashes)}")
        for h in start_hashes:
            validate_hex_hash(h)
        stop_hash = obj.get("stop_hash")
        if stop_hash is not None:
            validate_hex_hash(stop_hash)
        max_count = int(obj.get("max_count", 0))
        if max_count <= 0 or max_count > MAX_HEADERS_RESPONSE:
            raise NetworkValidationError(f"invalid max_count: {max_count}")
        return cls(
            start_hashes=[str(h) for h in start_hashes],
            stop_hash=str(stop_hash) if stop_hash is not None else None,
            max_count=max_count,
        )


@dataclass(frozen=True, slots=True)
class HeaderEntry:
    height: int
    hash: str
    header_bytes: str


@dataclass(frozen=True, slots=True)
class HeadersMessage:
    headers: list[HeaderEntry]

    def to_payload(self) -> bytes:
        return encode_payload({
            "headers": [
                {"height": h.height, "hash": h.hash, "header_bytes": h.header_bytes}
                for h in self.headers
            ]
        })

    @classmethod
    def from_payload(cls, payload: bytes) -> HeadersMessage:
        obj = decode_payload(payload)
        headers = obj.get("headers", [])
        if not isinstance(headers, list) or len(headers) > MAX_HEADERS_RESPONSE:
            raise NetworkValidationError(f"invalid headers length: {len(headers)}")
        entries: list[HeaderEntry] = []
        for entry in headers:
            validate_hex_hash(entry["hash"])
            validate_nonnegative_int(entry["height"])
            if not isinstance(entry.get("header_bytes"), str):
                raise NetworkValidationError("header_bytes must be a hex string")
            entries.append(HeaderEntry(
                height=int(entry["height"]),
                hash=str(entry["hash"]),
                header_bytes=str(entry["header_bytes"]),
            ))
        return cls(headers=entries)


@dataclass(frozen=True, slots=True)
class GetBlockMessage:
    hashes: list[str]
    max_total_bytes: int

    def to_payload(self) -> bytes:
        return encode_payload({
            "hashes": self.hashes,
            "max_total_bytes": self.max_total_bytes,
        })

    @classmethod
    def from_payload(cls, payload: bytes) -> GetBlockMessage:
        obj = decode_payload(payload)
        hashes = obj.get("hashes", [])
        if not isinstance(hashes, list) or len(hashes) > MAX_BLOCKS_RESPONSE:
            raise NetworkValidationError(f"invalid hashes length: {len(hashes)}")
        for h in hashes:
            validate_hex_hash(h)
        max_total_bytes = int(obj.get("max_total_bytes", 0))
        if max_total_bytes <= 0:
            raise NetworkValidationError(f"invalid max_total_bytes: {max_total_bytes}")
        return cls(hashes=[str(h) for h in hashes], max_total_bytes=max_total_bytes)


@dataclass(frozen=True, slots=True)
class BlockMessage:
    blocks: list[dict[str, str]]

    def to_payload(self) -> bytes:
        return encode_payload({"blocks": self.blocks})

    @classmethod
    def from_payload(cls, payload: bytes) -> BlockMessage:
        obj = decode_payload(payload)
        blocks = obj.get("blocks", [])
        if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS_RESPONSE:
            raise NetworkValidationError(f"invalid blocks length: {len(blocks)}")
        for b in blocks:
            if "hash" not in b or "block_bytes" not in b:
                raise NetworkValidationError("block entry missing hash or block_bytes")
            validate_hex_hash(b["hash"])
        return cls(blocks=[{"hash": str(b["hash"]), "block_bytes": str(b["block_bytes"])} for b in blocks])


@dataclass(frozen=True, slots=True)
class InventoryMessage:
    inv_type: str
    hashes: list[str]

    def to_payload(self) -> bytes:
        return encode_payload({"type": self.inv_type, "hashes": self.hashes})

    @classmethod
    def from_payload(cls, payload: bytes) -> InventoryMessage:
        obj = decode_payload(payload)
        inv_type = str(obj.get("type", ""))
        if inv_type not in {"headers", "blocks", "archive", "transactions"}:
            raise NetworkValidationError(f"invalid inventory type: {inv_type}")
        hashes = obj.get("hashes", [])
        if not isinstance(hashes, list) or len(hashes) > MAX_INVENTORY_ENTRIES:
            raise NetworkValidationError(f"invalid hashes length: {len(hashes)}")
        for h in hashes:
            validate_hex_hash(h)
        return cls(inv_type=inv_type, hashes=[str(h) for h in hashes])


@dataclass(frozen=True, slots=True)
class GetArchiveMessage:
    content_hash: str

    def to_payload(self) -> bytes:
        return encode_payload({"content_hash": self.content_hash})

    @classmethod
    def from_payload(cls, payload: bytes) -> GetArchiveMessage:
        obj = decode_payload(payload)
        if "content_hash" not in obj:
            raise NetworkValidationError("missing field: content_hash")
        validate_hex_hash(obj["content_hash"])
        return cls(content_hash=str(obj["content_hash"]))


@dataclass(frozen=True, slots=True)
class ArchiveMessage:
    content_hash: str

    def to_payload(self) -> bytes:
        return encode_payload({"content_hash": self.content_hash})

    @classmethod
    def from_payload(cls, payload: bytes) -> ArchiveMessage:
        obj = decode_payload(payload)
        if "content_hash" not in obj:
            raise NetworkValidationError("missing field: content_hash")
        validate_hex_hash(obj["content_hash"])
        return cls(content_hash=str(obj["content_hash"]))


@dataclass(frozen=True, slots=True)
class GetDataMessage:
    data_type: str
    hashes: list[str]

    def to_payload(self) -> bytes:
        return encode_payload({"type": self.data_type, "hashes": self.hashes})

    @classmethod
    def from_payload(cls, payload: bytes) -> GetDataMessage:
        obj = decode_payload(payload)
        data_type = str(obj.get("type", ""))
        if data_type not in {"headers", "blocks", "archive", "transactions"}:
            raise NetworkValidationError(f"invalid data type: {data_type}")
        hashes = obj.get("hashes", [])
        if not isinstance(hashes, list) or len(hashes) > MAX_INVENTORY_ENTRIES:
            raise NetworkValidationError(f"invalid hashes length: {len(hashes)}")
        for h in hashes:
            validate_hex_hash(h)
        return cls(data_type=data_type, hashes=[str(h) for h in hashes])


@dataclass(frozen=True, slots=True)
class RejectMessage:
    code: str
    reason: str
    offending_message_type: int | None

    def to_payload(self) -> bytes:
        obj: dict[str, Any] = {
            "code": self.code,
            "reason": self.reason,
        }
        if self.offending_message_type is not None:
            obj["offending_message_type"] = self.offending_message_type
        return encode_payload(obj)

    @classmethod
    def from_payload(cls, payload: bytes) -> RejectMessage:
        obj = decode_payload(payload)
        for key in ("code", "reason"):
            if key not in obj:
                raise NetworkValidationError(f"missing field: {key}")
        offending = obj.get("offending_message_type")
        return cls(
            code=str(obj["code"]),
            reason=str(obj["reason"]),
            offending_message_type=int(offending) if offending is not None else None,
        )


MESSAGE_PAYLOAD_CLASSES: dict[int, Any] = {
    HELLO: HelloMessage,
    HELLO_ACK: HelloAckMessage,
    PING: PingMessage,
    PONG: PongMessage,
    GET_HEADERS: GetHeadersMessage,
    HEADERS: HeadersMessage,
    GET_BLOCK: GetBlockMessage,
    BLOCK: BlockMessage,
    GET_ARCHIVE: GetArchiveMessage,
    ARCHIVE: ArchiveMessage,
    INVENTORY: InventoryMessage,
    GET_DATA: GetDataMessage,
    REJECT: RejectMessage,
}
