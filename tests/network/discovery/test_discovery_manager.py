from __future__ import annotations

from chainbreaker.network.discovery import (
    DiscoveryManager,
    MemoryBootstrapSource,
    PeerRecord,
    PeerSource,
    PeerStatus,
    StaticBootstrapSource,
)


def _rec(peer_id: str, host: str, port: int, source: PeerSource, score: int = 500) -> PeerRecord:
    return PeerRecord(peer_id=peer_id, host=host, port=port, source=source, score=score)


def test_manager_loads_static_bootstrap() -> None:
    source = StaticBootstrapSource([
        {"host": "10.0.0.1", "port": 8333, "trusted": True},
        {"host": "10.0.0.2", "port": 8333},
    ])
    manager = DiscoveryManager(bootstrap_sources=[source])
    added = manager.load_bootstrap()
    assert added == 2
    assert manager.peer_table.size == 2


def test_manager_selects_candidates_after_bootstrap() -> None:
    source = MemoryBootstrapSource([
        _rec("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP, score=900),
        _rec("p2", "10.0.0.2", 8333, PeerSource.BOOTSTRAP, score=800),
    ])
    manager = DiscoveryManager(bootstrap_sources=[source], max_outbound=1)
    candidates = manager.select_candidates()
    assert len(candidates) == 1
    assert candidates[0].peer_id == "p1"


def test_manager_handshake_success_updates_record() -> None:
    source = MemoryBootstrapSource([_rec("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP)])
    manager = DiscoveryManager(bootstrap_sources=[source])
    manager.load_bootstrap()
    assert manager.report_handshake_success("p1") is True
    rec = manager.peer_table.get("p1")
    assert rec is not None
    assert rec.status == PeerStatus.ACTIVE
    assert rec.score == 550


def test_manager_handshake_failure_bans_after_repeated_failures() -> None:
    source = MemoryBootstrapSource([_rec("p1", "10.0.0.1", 8333, PeerSource.BOOTSTRAP)])
    manager = DiscoveryManager(bootstrap_sources=[source])
    manager.load_bootstrap()
    for _ in range(3):
        manager.report_handshake_failure("p1")
    rec = manager.peer_table.get("p1")
    assert rec is not None
    assert rec.status == PeerStatus.BANNED
    assert rec.score == 0


def test_manager_add_discovered_uses_pex_source() -> None:
    manager = DiscoveryManager()
    rec = _rec("p2", "10.0.0.2", 8333, PeerSource.PEX, score=400)
    assert manager.add_discovered(rec) is True
    assert manager.peer_table.size == 1
