"""Block relay engine."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

from chainbreaker.block import BlockV2
from chainbreaker.chain import Ledger
from chainbreaker.network.messages import BlockMessage, GetBlockMessage, InventoryMessage
from chainbreaker.network.relay.cache import RelaySeenCache
from chainbreaker.network.relay.inventory import InventoryTracker
from chainbreaker.network.relay.limits import RelayLimitPolicy
from chainbreaker.storage import StorageBackend
from chainbreaker.storage.filesystem import StorageIOError


@dataclass(frozen=True, slots=True)
class RequestState:
    """State for an outstanding block request."""

    block_hash: str
    peer_id: str
    timestamp: float
    retry_count: int = 0


class RelayEngine:
    """Manage block announcements, requests, and relay decisions."""

    def __init__(
        self,
        ledger: Ledger,
        storage: StorageBackend,
        limits: RelayLimitPolicy | None = None,
        send_fn: Callable[[str, str, bytes], None] | None = None,
        peer_selector: Callable[[list[str]], list[str]] | None = None,
    ) -> None:
        self._ledger = ledger
        self._storage = storage
        self._limits = limits or RelayLimitPolicy()
        self._send_fn = send_fn
        self._peer_selector = peer_selector
        self._inventory = InventoryTracker(max_items=self._limits.max_inv_items)
        self._seen_cache = RelaySeenCache(
            max_entries=self._limits.seen_cache_size,
            ttl_seconds=self._limits.seen_cache_ttl_seconds,
        )
        self._pending_requests: dict[str, RequestState] = {}
        self._orphans: OrderedDict[str, tuple[BlockV2, float]] = OrderedDict()
        self._peer_inv_timestamps: dict[str, list[float]] = {}
        self._peer_get_timestamps: dict[str, list[float]] = {}
        self._local_blocks_to_announce: list[str] = []

    def on_local_block(self, block: BlockV2) -> None:
        """Called after consensus validates and accepts a new local block."""
        if self._seen_cache.has(block.hash):
            return
        self._seen_cache.add(block.hash, "local")
        self._local_blocks_to_announce.append(block.hash)

    def build_announcements(self) -> list[str]:
        """Return block hashes ready to announce, then clear the queue."""
        hashes = list(self._local_blocks_to_announce)
        self._local_blocks_to_announce.clear()
        return hashes

    def create_inv_message(self, peer_id: str, hashes: list[str] | None = None) -> InventoryMessage:
        """Create an inventory message for a peer."""
        target_hashes = hashes if hashes is not None else self.build_announcements()
        if not target_hashes:
            return InventoryMessage(inv_type="blocks", hashes=[])
        return InventoryMessage(inv_type="blocks", hashes=target_hashes[: self._limits.max_inv_items])

    def handle_inv(self, peer_id: str, payload: bytes, now: float | None = None) -> dict[str, Any]:
        """Process an inventory message from a peer."""
        if now is None:
            now = time.monotonic()
        msg = InventoryMessage.from_payload(payload)
        if msg.inv_type != "blocks":
            return {"status": "ignored", "reason": "not block inventory"}

        if not self._check_rate(self._peer_inv_timestamps, peer_id, self._limits.max_inv_per_peer_per_minute, now):
            return {"status": "rate_limited"}

        requested: list[str] = []
        for block_hash in msg.hashes:
            if self._seen_cache.has(block_hash, now):
                continue
            if len(self._pending_requests) >= self._limits.max_get_block_burst:
                break
            if block_hash in self._pending_requests:
                continue
            self._pending_requests[block_hash] = RequestState(
                block_hash=block_hash,
                peer_id=peer_id,
                timestamp=now,
            )
            requested.append(block_hash)

        return {"status": "requested", "hashes": requested}

    def next_get_block_requests(self, now: float | None = None) -> list[dict[str, Any]]:
        """Return GET_BLOCK request specs for pending requests."""
        if now is None:
            now = time.monotonic()
        requests: list[dict[str, Any]] = []
        for state in self._pending_requests.values():
            msg = GetBlockMessage(
                hashes=[state.block_hash],
                max_total_bytes=self._limits.max_block_bytes_total,
            )
            requests.append(
                {
                    "peer_id": state.peer_id,
                    "method": "GET_BLOCK",
                    "payload": msg.to_payload().decode("utf-8"),
                }
            )
        return requests

    def handle_block(self, peer_id: str, payload: bytes, now: float | None = None) -> dict[str, Any]:
        """Process a BLOCK response from a peer."""
        if now is None:
            now = time.monotonic()
        msg = BlockMessage.from_payload(payload)
        if len(msg.blocks) > self._limits.max_blocks_response:
            return {"status": "invalid", "reason": "too many blocks"}

        results: list[dict[str, Any]] = []
        for entry in msg.blocks:
            block_hash = entry["hash"]
            block = self._decode_block(entry["block_bytes"])
            if block.hash != block_hash:
                results.append({"hash": block_hash, "status": "invalid", "reason": "hash mismatch"})
                continue

            if self._seen_cache.has(block.hash, now):
                results.append({"hash": block.hash, "status": "duplicate"})
                self._pending_requests.pop(block.hash, None)
                continue

            # Consensus validation
            if not self._ledger.add_block_v2(block):
                results.append({"hash": block.hash, "status": "invalid", "reason": "consensus rejected"})
                self._pending_requests.pop(block.hash, None)
                continue

            # Commit through storage
            try:
                previous_state = self._ledger.registry_state_at(self._ledger.height() - 1)
                self._storage.append_block(block, previous_state=previous_state)
            except Exception as exc:
                results.append({"hash": block.hash, "status": "error", "reason": f"storage: {exc}"})
                self._pending_requests.pop(block.hash, None)
                continue

            self._seen_cache.add(block.hash, peer_id, now)
            self._pending_requests.pop(block.hash, None)
            self._local_blocks_to_announce.append(block.hash)
            self._try_connect_orphans(block.hash, now)
            results.append({"hash": block.hash, "status": "accepted"})

        return {"status": "processed", "results": results}

    def handle_get_block(self, peer_id: str, payload: bytes) -> dict[str, Any]:
        """Respond to a GET_BLOCK request from a peer."""
        msg = GetBlockMessage.from_payload(payload)
        if len(msg.hashes) > self._limits.max_blocks_response:
            return {"status": "rate_limited"}

        blocks: list[dict[str, str]] = []
        for block_hash in msg.hashes:
            height = self._ledger.height()
            block: BlockV2 | None = None
            for h in range(height + 1):
                try:
                    candidate = self._storage.read_block(h)
                except (KeyError, ValueError, StorageIOError):
                    continue
                if candidate.hash == block_hash:
                    block = candidate
                    break

            if block is None:
                continue
            blocks.append({"hash": block.hash, "block_bytes": self._encode_block(block)})
            if len(blocks) >= self._limits.max_blocks_response:
                break

        if not blocks:
            return {"status": "unknown"}

        response = BlockMessage(blocks=blocks)
        return {"status": "sent", "payload": response.to_payload().decode("utf-8")}

    def add_orphan(self, block: BlockV2, source_peer: str, now: float | None = None) -> None:
        """Store an orphan block reference with bounded memory."""
        if now is None:
            now = time.monotonic()
        if len(self._orphans) >= self._limits.max_orphan_blocks:
            self._orphans.popitem(last=False)
        expired = [h for h, (_, ts) in self._orphans.items() if now - ts > self._limits.orphan_max_age_seconds]
        for h in expired:
            self._orphans.pop(h, None)
        self._orphans[block.hash] = (block, now)

    def _try_connect_orphans(self, connected_hash: str, now: float) -> None:
        """Try to connect orphan blocks whose parent is now known."""
        connected: list[str] = []
        for h, (block, _) in self._orphans.items():
            if block.header.prev_hash == connected_hash:
                connected.append(h)
        for h in connected:
            self._orphans.pop(h, None)
            # Phase 8K does not recursively validate orphan chains; defer to future phase.

    def _check_rate(self, buckets: dict[str, list[float]], peer_id: str, limit_per_minute: int, now: float) -> bool:
        """Token-bucket-like per-peer rate check."""
        window = buckets.setdefault(peer_id, [])
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.pop(0)
        if len(window) >= limit_per_minute:
            return False
        window.append(now)
        return True

    def _decode_block(self, block_bytes_hex: str) -> BlockV2:
        import json

        data = json.loads(bytes.fromhex(block_bytes_hex).decode("utf-8"))
        return BlockV2.from_dict(data)

    def _encode_block(self, block: BlockV2) -> str:
        import json

        return json.dumps(block.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8").hex()
