"""Stream framing for envelope-based messages over TCP.

TCP is a byte stream. This module turns the stream back into discrete,
validated NetworkEnvelope objects. It performs length validation before
allocating attacker-controlled payload memory.
"""

from __future__ import annotations

import struct

from chainbreaker.network import NetworkEnvelope, parse_envelope
from chainbreaker.network.constants import (
    CBN1_MAGIC,
    FLAGS_SIZE,
    MAGIC_SIZE,
    MESSAGE_TYPE_SIZE,
    NETWORK_ID_LENGTH_SIZE,
    PAYLOAD_HASH_SIZE,
    PAYLOAD_LENGTH_SIZE,
)
from chainbreaker.network.socket.errors import SocketTransportLimitError
from chainbreaker.network.socket.limits import SocketLimits


class EnvelopeFraming:
    """Accumulates a TCP byte stream and yields complete NetworkEnvelope objects."""

    def __init__(self, limits: SocketLimits | None = None) -> None:
        self._limits = limits or SocketLimits()
        self._buffer = bytearray()

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()

    def consume(self, data: bytes) -> list[NetworkEnvelope]:
        """Append new bytes to the accumulator and return any complete envelopes."""
        if not data:
            return []

        if len(self._buffer) + len(data) > self._limits.max_frame_buffer_bytes:
            raise SocketTransportLimitError(
                f"frame buffer exceeded {self._limits.max_frame_buffer_bytes} bytes"
            )

        self._buffer.extend(data)
        envelopes: list[NetworkEnvelope] = []

        while True:
            before = len(self._buffer)
            envelope = self._try_parse_one()
            after = len(self._buffer)
            if envelope is not None:
                envelopes.append(envelope)
                continue
            # No envelope parsed. If the buffer shrank (e.g., garbage was
            # dropped), try again; otherwise we are waiting for more data.
            if after < before:
                continue
            break

        return envelopes

    def _try_parse_one(self) -> NetworkEnvelope | None:
        """If a complete envelope is present, consume it and return it."""
        buf = self._buffer

        if len(buf) < MAGIC_SIZE:
            return None

        if buf[:MAGIC_SIZE] != CBN1_MAGIC:
            # Discard leading bytes until the magic appears or the buffer is
            # too small. This is defensive resynchronization; production code
            # may prefer to disconnect on persistent mismatch.
            magic_pos = buf.find(CBN1_MAGIC)
            if magic_pos == -1:
                # No magic anywhere in the buffer; keep the last few bytes in
                # case a partial magic straddles the next read.
                keep = min(len(buf), MAGIC_SIZE - 1)
                if keep:
                    del buf[:-keep]
                else:
                    buf.clear()
                return None
            del buf[:magic_pos]
            return None

        # Need magic + version + network_id_len
        if len(buf) < MAGIC_SIZE + 2 + NETWORK_ID_LENGTH_SIZE:
            return None

        network_id_len = buf[MAGIC_SIZE + 2]
        if network_id_len == 0 or network_id_len > 64:
            del buf[:1]
            return None

        header_overhead = (
            MAGIC_SIZE
            + 2
            + NETWORK_ID_LENGTH_SIZE
            + network_id_len
            + MESSAGE_TYPE_SIZE
            + FLAGS_SIZE
            + PAYLOAD_LENGTH_SIZE
            + PAYLOAD_HASH_SIZE
        )
        if len(buf) < header_overhead:
            return None

        payload_length_offset = (
            MAGIC_SIZE + 2 + NETWORK_ID_LENGTH_SIZE + network_id_len + MESSAGE_TYPE_SIZE + FLAGS_SIZE
        )
        payload_length = struct.unpack(
            ">I", buf[payload_length_offset:payload_length_offset + PAYLOAD_LENGTH_SIZE]
        )[0]

        if payload_length > self._limits.max_message_size:
            raise SocketTransportLimitError(
                f"declared payload length {payload_length} exceeds max {self._limits.max_message_size}"
            )

        total_size = header_overhead + payload_length
        if total_size > self._limits.max_message_size:
            raise SocketTransportLimitError(
                f"declared message size {total_size} exceeds max {self._limits.max_message_size}"
            )

        if len(buf) < total_size:
            return None

        frame = bytes(buf[:total_size])
        del buf[:total_size]

        # parse_envelope validates magic, version, hash, etc.
        return parse_envelope(frame)
