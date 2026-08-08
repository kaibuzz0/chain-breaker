"""Network message envelope parsing and serialization.

All validation is performed before payload allocation where possible. The
payload is read only after its declared length has been bounds-checked.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from chainbreaker.crypto import HashEngine

from .constants import (
    CBN1_MAGIC,
    FLAG_COMPRESSED,
    FLAG_RESERVED_MASK,
    FLAGS_SIZE,
    KNOWN_MESSAGE_TYPES,
    MAGIC_SIZE,
    MAX_MESSAGE_SIZE,
    MAX_NETWORK_ID_LENGTH,
    MAX_PAYLOAD_BYTES,
    MESSAGE_TYPE_SIZE,
    MIN_ENVELOPE_SIZE,
    NET_PROTOCOL_VERSION,
    NETWORK_ID_BYTES,
    PAYLOAD_HASH_SIZE,
    PAYLOAD_LENGTH_SIZE,
    PROTOCOL_VERSION_SIZE,
)
from .errors import (
    NetworkValidationError,
    OversizedPayloadError,
    PayloadHashMismatchError,
    UnknownMessageTypeError,
)


@dataclass(frozen=True, slots=True)
class NetworkEnvelope:
    """Validated network message envelope.

    The payload is opaque bytes. Typed message parsing happens in
    `messages.py`.
    """

    message_type: int
    flags: int
    payload: bytes

    @property
    def requires_ack(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def compressed(self) -> bool:
        return bool(self.flags & FLAG_COMPRESSED)


def parse_envelope(data: bytes) -> NetworkEnvelope:
    """Parse and validate a complete message envelope from bytes.

    Raises NetworkValidationError (or subclasses) for any malformed or
    oversized input. Never allocates more than MAX_PAYLOAD_BYTES for the
    payload.
    """
    if len(data) < MIN_ENVELOPE_SIZE:
        raise NetworkValidationError(
            f"message too short: {len(data)} < {MIN_ENVELOPE_SIZE}"
        )
    if len(data) > MAX_MESSAGE_SIZE:
        raise NetworkValidationError(
            f"message too large: {len(data)} > {MAX_MESSAGE_SIZE}"
        )

    offset = 0

    magic = data[offset : offset + MAGIC_SIZE]
    offset += MAGIC_SIZE
    if magic != CBN1_MAGIC:
        raise NetworkValidationError(f"bad magic: {magic.hex()}")

    protocol_version = struct.unpack(">H", data[offset : offset + PROTOCOL_VERSION_SIZE])[0]
    offset += PROTOCOL_VERSION_SIZE
    if protocol_version != NET_PROTOCOL_VERSION:
        raise NetworkValidationError(
            f"unsupported protocol version: {protocol_version}"
        )

    network_id_len = data[offset]
    offset += 1
    if network_id_len == 0 or network_id_len > MAX_NETWORK_ID_LENGTH:
        raise NetworkValidationError(
            f"invalid network_id length: {network_id_len}"
        )

    expected_header_overhead = (
        MAGIC_SIZE
        + PROTOCOL_VERSION_SIZE
        + 1
        + network_id_len
        + MESSAGE_TYPE_SIZE
        + FLAGS_SIZE
        + PAYLOAD_LENGTH_SIZE
        + PAYLOAD_HASH_SIZE
    )
    if len(data) < expected_header_overhead:
        raise NetworkValidationError(
            f"message too short for declared network_id length {network_id_len}"
        )

    network_id = data[offset : offset + network_id_len]
    offset += network_id_len
    if network_id != NETWORK_ID_BYTES:
        raise NetworkValidationError(
            f"wrong network_id: {network_id.decode('utf-8', errors='replace')}"
        )

    message_type = data[offset]
    offset += MESSAGE_TYPE_SIZE
    if message_type not in KNOWN_MESSAGE_TYPES:
        raise UnknownMessageTypeError(
            f"unknown message type: {message_type}"
        )

    flags = data[offset]
    offset += FLAGS_SIZE
    if flags & FLAG_RESERVED_MASK:
        raise NetworkValidationError(
            f"reserved flags set: {flags:#04x}"
        )

    payload_length = struct.unpack(">I", data[offset : offset + PAYLOAD_LENGTH_SIZE])[0]
    offset += PAYLOAD_LENGTH_SIZE
    if payload_length > MAX_PAYLOAD_BYTES:
        raise OversizedPayloadError(
            f"payload length {payload_length} exceeds {MAX_PAYLOAD_BYTES}"
        )

    expected_total = expected_header_overhead + payload_length
    if len(data) != expected_total:
        raise NetworkValidationError(
            f"message size mismatch: got {len(data)}, expected {expected_total}"
        )

    payload_hash = data[offset : offset + PAYLOAD_HASH_SIZE]
    offset += PAYLOAD_HASH_SIZE

    payload = data[offset : offset + payload_length]

    computed_hash = HashEngine.sha256(payload)
    if payload_hash != computed_hash:
        raise PayloadHashMismatchError(
            f"payload hash mismatch: expected {payload_hash.hex()}, got {computed_hash.hex()}"
        )

    return NetworkEnvelope(message_type=message_type, flags=flags, payload=payload)


def serialize_envelope(message_type: int, flags: int = 0, payload: bytes = b"") -> bytes:
    """Serialize a message envelope.

    Enforces all protocol limits on the caller's payload.
    """
    if message_type not in KNOWN_MESSAGE_TYPES:
        raise UnknownMessageTypeError(f"unknown message type: {message_type}")
    if flags & FLAG_RESERVED_MASK:
        raise NetworkValidationError(f"reserved flags set: {flags:#04x}")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise OversizedPayloadError(
            f"payload length {len(payload)} exceeds {MAX_PAYLOAD_BYTES}"
        )

    payload_hash = HashEngine.sha256(payload)
    network_id_len = len(NETWORK_ID_BYTES)

    header = (
        CBN1_MAGIC
        + struct.pack(">H", NET_PROTOCOL_VERSION)
        + struct.pack(">B", network_id_len)
        + NETWORK_ID_BYTES
        + struct.pack(">B", message_type)
        + struct.pack(">B", flags)
        + struct.pack(">I", len(payload))
        + payload_hash
    )

    return header + payload
