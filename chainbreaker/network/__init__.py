"""Network protocol layer for Chain-Breaker.

This package implements the wire-format parser and message validation for
Network Protocol V1. It does not contain sockets, peers, discovery, sync, or
consensus logic.

Design rule: the network layer may propose data to the consensus core, but the
consensus core never depends on the network layer.
"""

from __future__ import annotations

from .constants import (
    ARCHIVE,
    BLOCK,
    CBN1_MAGIC,
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
    MAX_MESSAGE_SIZE,
    MAX_NETWORK_ID_LENGTH,
    MAX_PAYLOAD_BYTES,
    NET_PROTOCOL_VERSION,
    NETWORK_ID,
    PING,
    PONG,
    REJECT,
)
from .constants import (
    PEX as PEX,
)
from .envelope import NetworkEnvelope, parse_envelope, serialize_envelope
from .errors import (
    NetworkError,
    NetworkValidationError,
    OversizedPayloadError,
    PayloadHashMismatchError,
    UnknownMessageTypeError,
)
from .messages import (
    ArchiveMessage,
    BlockMessage,
    GetArchiveMessage,
    GetBlockMessage,
    GetDataMessage,
    GetHeadersMessage,
    HeadersMessage,
    HelloAckMessage,
    HelloMessage,
    InventoryMessage,
    PEXMessage,
    PingMessage,
    PongMessage,
    RejectMessage,
)

__all__ = [
    "ARCHIVE",
    "BLOCK",
    "CBN1_MAGIC",
    "GET_ARCHIVE",
    "GET_BLOCK",
    "GET_DATA",
    "GET_HEADERS",
    "HEADERS",
    "HELLO",
    "HELLO_ACK",
    "INVENTORY",
    "MAX_BLOCKS_RESPONSE",
    "MAX_HEADERS_RESPONSE",
    "MAX_INVENTORY_ENTRIES",
    "MAX_LOCATOR_SIZE",
    "MAX_MESSAGE_SIZE",
    "MAX_NETWORK_ID_LENGTH",
    "MAX_PAYLOAD_BYTES",
    "NET_PROTOCOL_VERSION",
    "NETWORK_ID",
    "PING",
    "PONG",
    "REJECT",
    "NetworkEnvelope",
    "parse_envelope",
    "serialize_envelope",
    "NetworkError",
    "NetworkValidationError",
    "OversizedPayloadError",
    "PayloadHashMismatchError",
    "UnknownMessageTypeError",
    "HelloMessage",
    "HelloAckMessage",
    "PingMessage",
    "PongMessage",
    "GetHeadersMessage",
    "HeadersMessage",
    "GetBlockMessage",
    "BlockMessage",
    "GetArchiveMessage",
    "ArchiveMessage",
    "InventoryMessage",
    "PEXMessage",
    "GetDataMessage",
    "RejectMessage",
]
