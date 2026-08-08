"""Discovery manager orchestrates peer sources and the peer table."""

from __future__ import annotations

from chainbreaker.network.discovery.bootstrap import BootstrapSource
from chainbreaker.network.discovery.errors import DiscoveryError
from chainbreaker.network.discovery.peer_table import PeerRecord, PeerStatus, PeerTable


class DiscoveryManager:
    """Aggregates bootstrap sources and maintains the peer table."""

    def __init__(
        self,
        table: PeerTable | None = None,
        bootstrap_sources: list[BootstrapSource] | None = None,
        max_outbound: int = 8,
    ) -> None:
        self._table = table or PeerTable()
        self._sources = list(bootstrap_sources or [])
        self._max_outbound = max(0, max_outbound)
        self._loaded = False

    @property
    def peer_table(self) -> PeerTable:
        return self._table

    def add_source(self, source: BootstrapSource) -> None:
        self._sources.append(source)

    def load_bootstrap(self) -> int:
        """Load candidates from all bootstrap sources into the peer table."""
        added = 0
        for source in self._sources:
            for rec in source.load():
                try:
                    self._table.add(rec)
                    added += 1
                except Exception as exc:
                    # A full table is not fatal for bootstrap loading.
                    if isinstance(exc, DiscoveryError):
                        break
        self._loaded = True
        return added

    def add_discovered(self, record: PeerRecord) -> bool:
        """Add a peer discovered via PEX or other non-bootstrap source."""
        try:
            return self._table.add(record)
        except DiscoveryError:
            return False

    def select_candidates(self) -> list[PeerRecord]:
        """Return deterministic connection candidates."""
        if not self._loaded:
            self.load_bootstrap()
        return self._table.select_candidates(self._max_outbound)

    def report_handshake_success(self, peer_id: str) -> bool:
        rec = self._table.get(peer_id)
        if rec is None:
            return False
        rec.touch_success()
        rec.status = PeerStatus.ACTIVE
        rec.score = min(1000, rec.score + 50)
        return True

    def report_handshake_failure(self, peer_id: str) -> bool:
        rec = self._table.get(peer_id)
        if rec is None:
            return False
        rec.touch_failure()
        rec.score = max(0, rec.score - 100)
        if rec.failure_count >= 3:
            rec.status = PeerStatus.BANNED
            rec.score = 0
        elif rec.status != PeerStatus.BANNED:
            rec.status = PeerStatus.FAILED
        return True

    def ban(self, peer_id: str) -> bool:
        return self._table.ban(peer_id)
