from __future__ import annotations

import json

import pytest

from chainbreaker.network import PEX, PING, PONG, NetworkEnvelope
from chainbreaker.network.gossip import GossipEngine, GossipError, GossipRateLimitError


def _pex_envelope(ttl: int = 3, hop_count: int = 0, peers: list[dict[str, object]] | None = None) -> NetworkEnvelope:
    payload = json.dumps({
        "peers": peers or [{"host": "10.0.0.1", "port": 8333}],
        "ttl": ttl,
        "hop_count": hop_count,
    }, sort_keys=True).encode()
    return NetworkEnvelope(message_type=PEX, flags=0, payload=payload)


def test_engine_accepts_valid_gossip() -> None:
    engine = GossipEngine()
    env = _pex_envelope()
    assert engine.receive(env, "peer-a") is True


def test_engine_rejects_non_gossip_message() -> None:
    engine = GossipEngine()
    env = NetworkEnvelope(message_type=0xFF, flags=0, payload=b"x")
    with pytest.raises(GossipError):
        engine.receive(env, "peer-a")


def test_engine_suppresses_duplicates() -> None:
    engine = GossipEngine()
    env = _pex_envelope()
    assert engine.receive(env, "peer-a") is True
    assert engine.receive(env, "peer-b") is False


def test_engine_payload_size_limit() -> None:
    engine = GossipEngine()
    env = NetworkEnvelope(message_type=PING, flags=0, payload=b"x" * 2048)
    with pytest.raises(GossipRateLimitError):
        engine.receive(env, "peer-a")


def test_engine_rate_limits_per_peer() -> None:
    engine = GossipEngine()
    env = _pex_envelope()
    # Default 10 per second; 11th should be rejected.
    with pytest.raises(GossipRateLimitError):
        for _ in range(11):
            engine.receive(env, "peer-a")


def test_forward_targets_respects_fanout() -> None:
    engine = GossipEngine()
    env = _pex_envelope()
    peers = [(f"peer-{i}", i) for i in range(10)]
    targets = engine.forward_targets(env, "peer-0", peers)
    assert len(targets) <= engine.limits.fanout
    assert all(t[0] != "peer-0" for t in targets)


def test_forward_targets_zero_ttl_no_forward() -> None:
    engine = GossipEngine()
    env = _pex_envelope(ttl=0)
    peers = [(f"peer-{i}", i) for i in range(10)]
    assert engine.forward_targets(env, "peer-0", peers) == []


def test_forward_targets_max_hops_no_forward() -> None:
    engine = GossipEngine()
    env = _pex_envelope(ttl=3, hop_count=8)
    peers = [(f"peer-{i}", i) for i in range(10)]
    assert engine.forward_targets(env, "peer-0", peers) == []


def test_prepare_forward_decrements_ttl() -> None:
    engine = GossipEngine()
    env = _pex_envelope(ttl=3, hop_count=1)
    forwarded = engine.prepare_forward(env)
    data = json.loads(forwarded.payload)
    assert data["ttl"] == 2
    assert data["hop_count"] == 2


def test_create_ping_pong_zero_ttl() -> None:
    engine = GossipEngine()
    ping = engine.create_ping(123)
    assert ping.message_type == PING
    data = json.loads(ping.payload)
    assert data["nonce"] == 123
    assert data["ttl"] == 0

    pong = engine.create_pong(123)
    assert pong.message_type == PONG
