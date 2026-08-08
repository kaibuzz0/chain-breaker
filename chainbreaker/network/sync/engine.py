"""Sync engine state machine and orchestration."""

from __future__ import annotations

from enum import Enum, auto
from typing import Any

from chainbreaker.block import NETWORK_ID, PROTOCOL_VERSION, BlockHeaderV2
from chainbreaker.chain import Ledger
from chainbreaker.network.sync.block_sync import BlockSync
from chainbreaker.network.sync.errors import SyncInvalidDataError, SyncStorageError
from chainbreaker.network.sync.header_sync import HeaderSync, header_hash
from chainbreaker.storage import StorageBackend


class SyncState(Enum):
    """States of the sync engine."""

    IDLE = auto()
    DISCOVERING_TIP = auto()
    REQUESTING_HEADERS = auto()
    VALIDATING_HEADERS = auto()
    REQUESTING_BLOCKS = auto()
    VALIDATING_BLOCKS = auto()
    COMMITTING = auto()
    SYNCED = auto()

    PEER_INVALID = auto()
    SYNC_TIMEOUT = auto()
    INVALID_DATA = auto()
    STORAGE_FAILURE = auto()
    RETRY_BACKOFF = auto()


class SyncEngine:
    """Orchestrate header and block sync with consensus and storage."""

    def __init__(
        self,
        ledger: Ledger,
        storage: StorageBackend,
        header_sync: HeaderSync | None = None,
        block_sync: BlockSync | None = None,
    ) -> None:
        self._ledger = ledger
        self._storage = storage
        self._header_sync = header_sync or HeaderSync(
            ledger=ledger,
            network_id=NETWORK_ID,
            protocol_version=PROTOCOL_VERSION,
        )
        self._block_sync = block_sync or BlockSync(ledger=ledger)
        self._state = SyncState.IDLE
        self._pending_headers: list[BlockHeaderV2] = []
        self._pending_blocks: list[Any] = []
        self._last_peer_id: str | None = None

    @property
    def state(self) -> SyncState:
        return self._state

    def start_header_sync(self) -> dict[str, Any]:
        """Return a `GET_HEADERS` request payload."""
        self._state = SyncState.REQUESTING_HEADERS
        msg = self._header_sync.create_get_headers()
        return {"method": "GET_HEADERS", "payload": msg.to_payload().decode("utf-8")}

    def handle_headers(self, peer_id: str, payload: bytes) -> dict[str, Any]:
        """Process a `HEADERS` response."""
        self._last_peer_id = peer_id
        self._state = SyncState.VALIDATING_HEADERS
        try:
            from chainbreaker.network.messages import HeadersMessage

            msg = HeadersMessage.from_payload(payload)
            headers = self._header_sync.parse_headers_message(msg)
        except SyncInvalidDataError as exc:
            self._state = SyncState.INVALID_DATA
            return {"status": "invalid", "reason": str(exc)}

        if not headers:
            self._state = SyncState.SYNCED
            return {"status": "synced"}

        new_work = self._header_sync.compute_chain_work(headers)
        local_work = self._ledger.chain_work()
        if new_work <= local_work:
            self._state = SyncState.SYNCED
            return {"status": "no_better_chain"}

        self._pending_headers = headers
        self._state = SyncState.REQUESTING_BLOCKS
        return {"status": "request_blocks", "count": len(headers)}

    def next_block_request(self) -> dict[str, Any] | None:
        """Return the next `GET_BLOCK` request, or None if done."""
        if not self._pending_headers:
            return None
        header = self._pending_headers[0]
        return {
            "method": "GET_BLOCK",
            "hash": header_hash(header),
        }

    def handle_block(self, peer_id: str, payload: bytes) -> dict[str, Any]:
        """Process a `BLOCK` response."""
        self._last_peer_id = peer_id
        if not self._pending_headers:
            return {"status": "unexpected_block"}

        self._state = SyncState.VALIDATING_BLOCKS
        expected_height = self._ledger.height() + 1 + len(self._pending_blocks)
        expected_prev_hash = (
            self._pending_blocks[-1].hash
            if self._pending_blocks
            else self._ledger.last_block.hash
        )

        try:
            from chainbreaker.network.messages import BlockMessage

            msg = BlockMessage.from_payload(payload)
            block = self._block_sync.parse_block_message(msg, expected_height, expected_prev_hash)
        except SyncInvalidDataError as exc:
            self._state = SyncState.INVALID_DATA
            return {"status": "invalid", "reason": str(exc)}

        # Full ledger validation (state transition, registry, archive).
        if not self._ledger.add_block_v2(block):
            self._state = SyncState.INVALID_DATA
            return {"status": "invalid", "reason": "ledger rejected block"}

        self._pending_blocks.append(block)
        self._pending_headers.pop(0)

        if self._pending_headers:
            self._state = SyncState.REQUESTING_BLOCKS
            return {"status": "next_block"}

        return self._commit()

    def _commit(self) -> dict[str, Any]:
        """Persist the validated chain extension atomically."""
        self._state = SyncState.COMMITTING
        try:
            for block in self._pending_blocks:
                prev_state = self._ledger.registry_state_at(self._ledger.height() - 1)
                self._storage.append_block(block, previous_state=prev_state)
        except Exception as exc:
            self._state = SyncState.STORAGE_FAILURE
            raise SyncStorageError(f"storage commit failed: {exc}") from exc
        finally:
            self._pending_blocks.clear()

        self._state = SyncState.SYNCED
        return {"status": "committed", "new_height": self._ledger.height()}

    def reset(self) -> None:
        """Clear pending state for retry or idle."""
        self._state = SyncState.IDLE
        self._pending_headers.clear()
        self._pending_blocks.clear()
