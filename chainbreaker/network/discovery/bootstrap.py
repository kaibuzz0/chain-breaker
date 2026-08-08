"""Bootstrap discovery sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from chainbreaker.network.discovery.peer_table import PeerRecord, PeerSource


class BootstrapSource(ABC):
    """Abstract source of peer candidates."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name."""

    @abstractmethod
    def load(self) -> list[PeerRecord]:
        """Return a list of candidate peer records."""


class StaticBootstrapSource(BootstrapSource):
    """Bootstrap source from a static configuration list."""

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self._entries = entries

    @property
    def name(self) -> str:
        return "static_bootstrap"

    def load(self) -> list[PeerRecord]:
        records: list[PeerRecord] = []
        for idx, entry in enumerate(self._entries):
            host = entry.get("host", "")
            port = entry.get("port", 0)
            if not host or not port:
                continue
            trusted = bool(entry.get("trusted", False))
            score = 900 if trusted else 600
            rec = PeerRecord(
                peer_id=f"{self.name}-{idx}-{host}-{port}",
                host=host,
                port=port,
                source=PeerSource.BOOTSTRAP,
                score=score,
                capabilities={"trusted": trusted},
            )
            records.append(rec)
        return records


class MemoryBootstrapSource(BootstrapSource):
    """In-memory bootstrap source for tests."""

    def __init__(self, records: list[PeerRecord]) -> None:
        self._records = records

    @property
    def name(self) -> str:
        return "memory_bootstrap"

    def load(self) -> list[PeerRecord]:
        return list(self._records)
