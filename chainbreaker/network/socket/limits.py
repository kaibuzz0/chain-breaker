"""Socket-specific resource limits."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SocketLimits:
    """Resource limits for a single socket connection."""

    # Maximum bytes the framing accumulator may hold before a complete envelope.
    max_frame_buffer_bytes: int = 8_388_608  # 8 MiB

    # Maximum total bytes in a single message envelope.
    max_message_size: int = 2_097_152  # 2 MiB + envelope overhead

    # Seconds to wait for a complete frame.
    read_timeout_seconds: float = 30.0

    # Seconds to wait for a write to complete.
    write_timeout_seconds: float = 30.0

    # Seconds to wait for a connection to be established.
    connect_timeout_seconds: float = 10.0

    # Backlog for server listen().
    listen_backlog: int = 128

    # Default TCP receive buffer size used by framing reads.
    recv_buffer_size: int = 65_536
