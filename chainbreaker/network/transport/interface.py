"""Abstract transport interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from chainbreaker.network.envelope import NetworkEnvelope


class Transport(ABC):
    """Abstract byte/message transport.

    Implementations may use sockets, in-memory channels, or any other
    mechanism, but the consensus layer must never depend on a concrete
    transport.
    """

    @property
    @abstractmethod
    def is_open(self) -> bool:
        """Return True if the transport is open and usable."""

    @abstractmethod
    async def send(self, envelope: NetworkEnvelope) -> None:
        """Send a validated network envelope."""

    @abstractmethod
    async def receive(self) -> NetworkEnvelope:
        """Receive the next validated network envelope."""

    @abstractmethod
    async def close(self) -> None:
        """Close the transport gracefully."""

    @abstractmethod
    async def status(self) -> dict[str, Any]:
        """Return a snapshot of transport health/limits."""
