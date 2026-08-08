"""Default relay resource limits."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RelayLimitPolicy:
    """Resource policy for the relay layer."""

    max_inv_items: int = 256
    max_inv_per_peer_per_minute: int = 60
    max_inv_burst: int = 10
    max_get_block_per_peer_per_minute: int = 120
    max_get_block_burst: int = 16
    max_blocks_response: int = 32
    max_block_bytes_total: int = 2_000_000
    block_response_timeout_seconds: float = 30.0
    max_block_retries: int = 3
    seen_cache_size: int = 50_000
    seen_cache_ttl_seconds: float = 7_200.0
    max_orphan_blocks: int = 1_024
    orphan_max_age_seconds: float = 7_200.0
    orphan_parent_request_timeout_seconds: float = 60.0
    relay_bytes_per_peer_per_minute: int = 10 * 1024 * 1024
    relay_bytes_global_per_minute: int = 50 * 1024 * 1024


DEFAULT_RELAY_LIMITS = RelayLimitPolicy()
