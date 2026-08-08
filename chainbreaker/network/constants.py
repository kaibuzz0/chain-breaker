"""Network Protocol V1 constants."""

from __future__ import annotations

# Wire protocol family magic: "CBN1" (Chain-Breaker Network v1)
CBN1_MAGIC = b"\x43\x42\x4E\x31"

# Wire protocol version. This is NOT the consensus protocol version.
NET_PROTOCOL_VERSION = 1

# Network ID shared with Protocol V2.
NETWORK_ID = "chainbreaker-scripture-v2"
NETWORK_ID_BYTES = NETWORK_ID.encode("utf-8")

# Envelope field sizes (bytes).
MAGIC_SIZE = 4
PROTOCOL_VERSION_SIZE = 2
NETWORK_ID_LENGTH_SIZE = 1
MESSAGE_TYPE_SIZE = 1
FLAGS_SIZE = 1
PAYLOAD_LENGTH_SIZE = 4
PAYLOAD_HASH_SIZE = 32

# Fixed header size for the canonical network ID.
ENVELOPE_HEADER_SIZE = (
    MAGIC_SIZE
    + PROTOCOL_VERSION_SIZE
    + NETWORK_ID_LENGTH_SIZE
    + len(NETWORK_ID_BYTES)
    + MESSAGE_TYPE_SIZE
    + FLAGS_SIZE
    + PAYLOAD_LENGTH_SIZE
    + PAYLOAD_HASH_SIZE
)

# Minimum envelope size with the canonical network ID.
MIN_ENVELOPE_SIZE = (
    MAGIC_SIZE
    + PROTOCOL_VERSION_SIZE
    + NETWORK_ID_LENGTH_SIZE
    + len(NETWORK_ID_BYTES)
    + MESSAGE_TYPE_SIZE
    + FLAGS_SIZE
    + PAYLOAD_LENGTH_SIZE
    + PAYLOAD_HASH_SIZE
)

# Maximum payload length any single message may carry.
MAX_PAYLOAD_BYTES = 2_000_000

# Maximum total message size on the wire.
MAX_MESSAGE_SIZE = ENVELOPE_HEADER_SIZE + MAX_PAYLOAD_BYTES

# Maximum network ID length permitted by the envelope format.
MAX_NETWORK_ID_LENGTH = 64

# Message type enumeration.
HELLO = 0x01
HELLO_ACK = 0x02
PING = 0x03
PONG = 0x04
GET_HEADERS = 0x05
HEADERS = 0x06
GET_BLOCK = 0x07
BLOCK = 0x08
GET_ARCHIVE = 0x09
ARCHIVE = 0x0A
INVENTORY = 0x0B
GET_DATA = 0x0C
REJECT = 0x0D

KNOWN_MESSAGE_TYPES = {
    HELLO,
    HELLO_ACK,
    PING,
    PONG,
    GET_HEADERS,
    HEADERS,
    GET_BLOCK,
    BLOCK,
    GET_ARCHIVE,
    ARCHIVE,
    INVENTORY,
    GET_DATA,
    REJECT,
}

# Flag bits.
FLAG_REQUIRES_ACK = 0x01
FLAG_COMPRESSED = 0x02
FLAG_RESERVED_MASK = 0xFC  # bits 2-7 must be zero in V1

# Sync/response limits.
MAX_HEADERS_RESPONSE = 2000
MAX_BLOCKS_RESPONSE = 32
MAX_INVENTORY_ENTRIES = 5000
MAX_LOCATOR_SIZE = 32

# Gossip-specific message types and limits.
PEX = 0x0E  # peer exchange
GOSSIP_MESSAGE_TYPES = {PING, PONG, PEX}

DEFAULT_GOSSIP_TTL = 3
DEFAULT_GOSSIP_FANOUT = 3
DEFAULT_GOSSIP_MAX_HOPS = 8
DEFAULT_GOSSIP_CACHE_TTL_SECONDS = 300
DEFAULT_GOSSIP_CACHE_MAX_ENTRIES = 50_000
DEFAULT_MAX_GOSSIP_PAYLOAD_SIZE = 1024
