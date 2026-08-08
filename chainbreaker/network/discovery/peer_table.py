"""Peer table data structures and rules."""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from chainbreaker.network.discovery.errors import PeerTableFullError


class PeerSource(Enum):
    """Where a peer candidate originated."""

    BOOTSTRAP = auto()
    DNS = auto()
    MANUAL = auto()
    PEX = auto()
    CACHE = auto()


class PeerStatus(Enum):
    """Lifecycle status of a peer record."""

    CANDIDATE = auto()
    CONNECTING = auto()
    ACTIVE = auto()
    FAILED = auto()
    BANNED = auto()


@dataclass
class PeerRecord:
    """A known peer and its metadata."""

    peer_id: str
    host: str
    port: int
    source: PeerSource
    score: int = 500
    capabilities: dict[str, Any] = field(default_factory=dict)
    last_seen: float | None = None
    last_attempt: float | None = None
    failure_count: int = 0
    status: PeerStatus = PeerStatus.CANDIDATE

    @property
    def address(self) -> tuple[str, int]:
        return (self.host, self.port)

    def touch_attempt(self) -> None:
        self.last_attempt = time.monotonic()

    def touch_success(self) -> None:
        now = time.monotonic()
        self.last_seen = now
        self.last_attempt = now
        self.failure_count = 0

    def touch_failure(self) -> None:
        self.failure_count += 1

    def is_banned(self) -> bool:
        return self.status == PeerStatus.BANNED


class PeerTable:
    """Bounded, diversity-aware collection of known peers."""

    def __init__(
        self,
        max_entries: int = 4096,
        max_same_source_ratio: float = 0.25,
        max_same_prefix_peers: int = 2,
        ipv4_prefix_bits: int = 24,
        ipv6_prefix_bits: int = 48,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._max_same_source_ratio = max(0.0, min(1.0, max_same_source_ratio))
        self._max_same_prefix_peers = max(0, max_same_prefix_peers)
        self._ipv4_prefix_bits = ipv4_prefix_bits
        self._ipv6_prefix_bits = ipv6_prefix_bits
        self._records: dict[str, PeerRecord] = {}
        self._address_index: dict[tuple[str, int], str] = {}

    @property
    def size(self) -> int:
        return len(self._records)

    def get(self, peer_id: str) -> PeerRecord | None:
        return self._records.get(peer_id)

    def all(self) -> list[PeerRecord]:
        return list(self._records.values())

    def add(self, record: PeerRecord) -> bool:
        """Add or update a peer record. Returns True if newly inserted."""
        existing = self._records.get(record.peer_id)
        if existing is not None:
            self._update_existing(existing, record)
            return False
        addr = (record.host, record.port)
        if addr in self._address_index:
            # Same endpoint under a different peer_id: merge into existing key.
            existing_id = self._address_index[addr]
            self._update_existing(self._records[existing_id], record)
            return False
        if self.size >= self._max_entries and not self._evict_for(record):
            raise PeerTableFullError("peer table capacity reached")
        self._records[record.peer_id] = record
        self._address_index[addr] = record.peer_id
        return True

    def _update_existing(self, existing: PeerRecord, record: PeerRecord) -> None:
        # Preserve highest score, most recent metadata, merge capabilities.
        if record.score > existing.score:
            existing.score = record.score
        if record.capabilities:
            existing.capabilities.update(record.capabilities)
        if record.last_seen is not None and (existing.last_seen is None or record.last_seen > existing.last_seen):
            existing.last_seen = record.last_seen

    def remove(self, peer_id: str) -> bool:
        rec = self._records.pop(peer_id, None)
        if rec is None:
            return False
        self._address_index.pop((rec.host, rec.port), None)
        return True

    def ban(self, peer_id: str) -> bool:
        rec = self._records.get(peer_id)
        if rec is None:
            return False
        rec.status = PeerStatus.BANNED
        return True

    def select_candidates(
        self,
        count: int,
        require_source_diversity: bool = True,
    ) -> list[PeerRecord]:
        """Return up to `count` viable peer candidates deterministically."""
        if count <= 0:
            return []
        viable = [
            rec for rec in self._records.values()
            if rec.status in (PeerStatus.CANDIDATE, PeerStatus.FAILED)
            and not rec.is_banned()
        ]
        # Stable ordering by score descending, then recency, then peer_id.
        viable.sort(key=lambda r: (-r.score, -(r.last_seen or 0.0), r.peer_id))
        chosen: list[PeerRecord] = []
        source_counts: dict[PeerSource, int] = {}
        prefix_counts: dict[str, int] = {}
        max_per_source = max(1, int(self._max_same_source_ratio * count))
        for rec in viable:
            if len(chosen) >= count:
                break
            if require_source_diversity:
                src_total = source_counts.get(rec.source, 0)
                if src_total >= max_per_source:
                    continue
                prefix = self._network_prefix(rec.host)
                if prefix and prefix_counts.get(prefix, 0) >= self._max_same_prefix_peers:
                    continue
                source_counts[rec.source] = src_total + 1
                if prefix:
                    prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
            chosen.append(rec)
        return chosen

    def _network_prefix(self, host: str) -> str | None:
        try:
            addr = ipaddress.ip_address(host)
            if isinstance(addr, ipaddress.IPv4Address):
                network = ipaddress.ip_network(f"{host}/{self._ipv4_prefix_bits}", strict=False)
            elif isinstance(addr, ipaddress.IPv6Address):
                network = ipaddress.ip_network(f"{host}/{self._ipv6_prefix_bits}", strict=False)
            else:
                return None
            return str(network.network_address)
        except ValueError:
            return None

    def _evict_for(self, candidate: PeerRecord) -> bool:
        """Evict the worst record to make room for `candidate`.

        Only evict banned peers, or same-source peers with strictly lower
        score, so that high-quality records are not churned by equally good
        candidates.
        """
        if not self._records:
            return False

        candidates_to_evict = [
            rec for rec in self._records.values()
            if rec.status == PeerStatus.BANNED
            or (rec.source == candidate.source and rec.score < candidate.score)
        ]
        if not candidates_to_evict:
            return False
        # Pick lowest score, then oldest last_seen, then peer_id for stability.
        victim = min(candidates_to_evict, key=lambda r: (r.score, r.last_seen or 0.0, r.peer_id))
        return self.remove(victim.peer_id)
