from __future__ import annotations

import pytest

from chainbreaker.network.discovery import (
    PeerRecord,
    PeerSource,
    PeerTable,
    PeerTableFullError,
)


def _record(peer_id: str, host: str, port: int, source: PeerSource, score: int = 500) -> PeerRecord:
    return PeerRecord(
        peer_id=peer_id,
        host=host,
        port=port,
        source=source,
        score=score,
    )


def test_peer_table_add_and_get() -> None:
    table = PeerTable()
    rec = _record("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP)
    assert table.add(rec) is True
    found = table.get("p1")
    assert found is not None
    assert found.address == ("10.0.0.1", 8333)


def test_peer_table_update_existing_preserves_best_metadata() -> None:
    table = PeerTable()
    table.add(_record("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP, score=500))
    table.add(_record("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP, score=700))
    rec = table.get("p1")
    assert rec is not None
    assert rec.score == 700


def test_peer_table_capacity_evicts_lowest_score() -> None:
    table = PeerTable(max_entries=2)
    table.add(_record("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP, score=300))
    table.add(_record("p2", "10.0.0.2", 8333, PeerSource.BOOTSTRAP, score=200))
    table.add(_record("p3", "10.0.0.3", 8333, PeerSource.BOOTSTRAP, score=500))
    assert table.size == 2
    assert table.get("p2") is None


def test_peer_table_full_when_no_eviction_possible() -> None:
    table = PeerTable(max_entries=1)
    table.add(_record("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP, score=1000))
    with pytest.raises(PeerTableFullError):
        table.add(_record("p2", "10.0.0.2", 8333, PeerSource.BOOTSTRAP, score=1000))


def test_peer_table_select_candidates_sorted_by_score() -> None:
    table = PeerTable(max_same_source_ratio=1.0, max_same_prefix_peers=10)
    table.add(_record("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP, score=400))
    table.add(_record("p2", "10.0.0.2", 8333, PeerSource.BOOTSTRAP, score=900))
    table.add(_record("p3", "10.0.0.3", 8333, PeerSource.BOOTSTRAP, score=600))
    chosen = table.select_candidates(2)
    assert [r.peer_id for r in chosen] == ["p2", "p3"]


def test_peer_table_ban_removes_from_candidates() -> None:
    table = PeerTable()
    table.add(_record("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP))
    table.ban("p1")
    chosen = table.select_candidates(1)
    assert chosen == []


def test_peer_table_source_diversity_enforced() -> None:
    table = PeerTable(max_entries=10, max_same_source_ratio=0.5, max_same_prefix_peers=10)
    table.add(_record("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP, score=900))
    table.add(_record("p2", "10.0.0.2", 8333, PeerSource.BOOTSTRAP, score=800))
    table.add(_record("p3", "10.0.0.3", 8333, PeerSource.MANUAL, score=700))
    chosen = table.select_candidates(3)
    assert len(chosen) == 2
    sources = {r.source for r in chosen}
    assert len(sources) >= 2


def test_peer_table_prefix_diversity_enforced() -> None:
    table = PeerTable(max_entries=10, max_same_source_ratio=1.0, max_same_prefix_peers=1)
    table.add(_record("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP, score=900))
    table.add(_record("p2", "10.0.0.2", 8333, PeerSource.BOOTSTRAP, score=800))
    table.add(_record("p3", "10.0.1.1", 8333, PeerSource.BOOTSTRAP, score=700))
    chosen = table.select_candidates(3)
    assert len(chosen) == 2
    prefixes = {r.host.rsplit(".", 1)[0] for r in chosen}
    assert len(prefixes) == 2
