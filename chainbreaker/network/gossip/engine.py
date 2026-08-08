"""Bounded gossip propagation engine."""

from __future__ import annotations

import time
from dataclasses import dataclass

from chainbreaker.network.constants import (
    DEFAULT_GOSSIP_FANOUT,
    DEFAULT_GOSSIP_MAX_HOPS,
    DEFAULT_MAX_GOSSIP_PAYLOAD_SIZE,
    GOSSIP_MESSAGE_TYPES,
    PING,
    PONG,
)
from chainbreaker.network.envelope import NetworkEnvelope
from chainbreaker.network.gossip.cache import GossipCache
from chainbreaker.network.gossip.errors import GossipError, GossipRateLimitError


@dataclass(frozen=True)
class GossipLimits:
    """Resource limits for the gossip engine."""

    fanout: int = DEFAULT_GOSSIP_FANOUT
    max_hops: int = DEFAULT_GOSSIP_MAX_HOPS
    max_payload_size: int = DEFAULT_MAX_GOSSIP_PAYLOAD_SIZE
    max_per_peer_per_second: float = 10.0
    max_total_per_second: float = 100.0
    max_bytes_per_second: float = 512 * 1024


class TokenBucket:
    """Simple token bucket for rate limiting."""

    def __init__(self, rate: float, capacity: float | None = None) -> None:
        self._rate = float(rate)
        self._capacity = float(capacity if capacity is not None else rate)
        self._tokens = self._capacity
        self._last = time.monotonic()

    def consume(self, amount: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self._last
        self._last = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        if self._tokens < amount:
            return False
        self._tokens -= amount
        return True


class GossipEngine:
    """Route gossip messages through active peers within bounded limits."""

    def __init__(
        self,
        limits: GossipLimits | None = None,
        cache: GossipCache | None = None,
    ) -> None:
        self._limits = limits or GossipLimits()
        self._cache = cache or GossipCache()
        self._peer_buckets: dict[str, TokenBucket] = {}
        self._total_bucket = TokenBucket(self._limits.max_total_per_second)
        self._bytes_bucket = TokenBucket(self._limits.max_bytes_per_second)

    @property
    def limits(self) -> GossipLimits:
        return self._limits

    @property
    def cache(self) -> GossipCache:
        return self._cache

    def _check_rate(self, peer_id: str, payload_size: int) -> None:
        if payload_size > self._limits.max_payload_size:
            raise GossipRateLimitError("gossip payload too large")
        peer_bucket = self._peer_buckets.setdefault(
            peer_id, TokenBucket(self._limits.max_per_peer_per_second)
        )
        if not peer_bucket.consume(1.0):
            raise GossipRateLimitError("peer gossip rate limit exceeded")
        if not self._total_bucket.consume(1.0):
            raise GossipRateLimitError("global gossip rate limit exceeded")
        if not self._bytes_bucket.consume(payload_size):
            raise GossipRateLimitError("global gossip byte limit exceeded")

    def receive(
        self,
        envelope: NetworkEnvelope,
        from_peer_id: str,
    ) -> bool:
        """Process an inbound gossip message. Return True if accepted."""
        if envelope.message_type not in GOSSIP_MESSAGE_TYPES:
            raise GossipError(f"message type {envelope.message_type} is not gossip")
        self._check_rate(from_peer_id, len(envelope.payload))
        if self._cache.seen(envelope.message_type, envelope.payload):
            return False
        self._cache.add(envelope.message_type, envelope.payload)
        return True

    def forward_targets(
        self,
        envelope: NetworkEnvelope,
        from_peer_id: str,
        peers: list[tuple[str, int]],
    ) -> list[tuple[str, int]]:
        """Select peers to forward a gossip message to."""
        if envelope.message_type not in GOSSIP_MESSAGE_TYPES:
            return []
        ttl, hop_count = self._extract_forward_fields(envelope.payload)
        if ttl <= 0 or hop_count >= self._limits.max_hops:
            return []

        available = [p for p in peers if p[0] != from_peer_id]
        # Deterministic ordering by peer_id then stable fanout using the message
        # hash as a seed source. A fixed seed makes unit tests reproducible.
        seed = int(self._cache._gossip_id(envelope.message_type, envelope.payload)[:16], 16)
        available.sort(key=lambda p: (hash((seed, p[0])) % (2**31), p[0]))
        return available[: self._limits.fanout]

    def prepare_forward(
        self,
        envelope: NetworkEnvelope,
    ) -> NetworkEnvelope:
        """Return a new envelope with decremented TTL and incremented hop count."""
        ttl, hop_count = self._extract_forward_fields(envelope.payload)
        new_payload = self._adjust_fields(envelope.payload, ttl - 1, hop_count + 1)
        return NetworkEnvelope(
            message_type=envelope.message_type,
            flags=envelope.flags,
            payload=new_payload,
        )

    def _extract_forward_fields(self, payload: bytes) -> tuple[int, int]:
        """Read ttl/hop_count from gossip payloads. Defaults to 0/0."""
        try:
            import json

            data = json.loads(payload)
            if isinstance(data, dict):
                return int(data.get("ttl", 0)), int(data.get("hop_count", 0))
        except Exception:  # nosec B110
            pass
        return 0, 0

    def _adjust_fields(self, payload: bytes, ttl: int, hop_count: int) -> bytes:
        try:
            import json

            data = json.loads(payload)
            if isinstance(data, dict):
                data["ttl"] = max(0, ttl)
                data["hop_count"] = hop_count
                return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        except Exception:  # nosec B110
            pass
        return payload

    def create_ping(self, nonce: int) -> NetworkEnvelope:
        import json

        payload = json.dumps({"nonce": nonce, "ttl": 0, "hop_count": 0}, sort_keys=True).encode("utf-8")
        return NetworkEnvelope(message_type=PING, flags=0, payload=payload)

    def create_pong(self, nonce: int) -> NetworkEnvelope:
        import json

        payload = json.dumps({"nonce": nonce, "ttl": 0, "hop_count": 0}, sort_keys=True).encode("utf-8")
        return NetworkEnvelope(message_type=PONG, flags=0, payload=payload)
