"""Header synchronization logic."""

from __future__ import annotations

import json

from chainbreaker.block import BlockHeaderV2, satisfies_pow
from chainbreaker.chain import Ledger
from chainbreaker.codec import BinaryCodec
from chainbreaker.crypto import HashEngine, work_for_target_v2
from chainbreaker.network.constants import MAX_HEADERS_RESPONSE, MAX_LOCATOR_SIZE
from chainbreaker.network.messages import GetHeadersMessage, HeadersMessage
from chainbreaker.network.sync.errors import SyncInvalidDataError


class HeaderSync:
    """Download and validate header chains from peers."""

    def __init__(self, ledger: Ledger, network_id: str, protocol_version: int) -> None:
        self._ledger = ledger
        self._network_id = network_id
        self._protocol_version = protocol_version

    def build_locator(self) -> list[str]:
        """Sparse header locator from local tip back to genesis."""
        locator: list[str] = []
        step = 1
        height = self._ledger.height()
        while height > 0 and len(locator) < MAX_LOCATOR_SIZE - 1:
            block = self._ledger.chain[height]
            locator.append(block.hash)
            height -= step
            if len(locator) > 10:
                step *= 2
        locator.append(self._ledger.genesis_hash())
        return locator

    def create_get_headers(self) -> GetHeadersMessage:
        return GetHeadersMessage(
            start_hashes=self.build_locator(),
            stop_hash=None,
            max_count=MAX_HEADERS_RESPONSE,
        )

    def encode_header(self, header: BlockHeaderV2) -> str:
        """Serialize a v2 header to a hex string for wire transport."""
        codec = BinaryCodec()
        return codec.encode_header_v2(header.to_dict()).hex()

    def parse_headers_message(self, message: HeadersMessage) -> list[BlockHeaderV2]:
        """Validate a sequence of headers against local chain and rules."""
        headers: list[BlockHeaderV2] = []
        prev_hash = self._ledger.last_block.hash if self._ledger.chain else self._ledger.genesis_hash()
        expected_height = self._ledger.height() + 1
        for idx, entry in enumerate(message.headers):
            try:
                header = self._decode_header(entry.header_bytes)
            except Exception as exc:
                raise SyncInvalidDataError(f"header {idx}: decode failed: {exc}") from exc

            if header.prev_hash != prev_hash:
                raise SyncInvalidDataError(f"header {idx}: prev_hash mismatch")
            expected_target = self._ledger.expected_target_at(expected_height)
            if header.target != expected_target:
                raise SyncInvalidDataError(f"header {idx}: unexpected target")
            if not satisfies_pow(header.hash(), header.target):
                raise SyncInvalidDataError(f"header {idx}: PoW check failed")
            if header.version != self._protocol_version:
                raise SyncInvalidDataError(f"header {idx}: version mismatch")

            headers.append(header)
            prev_hash = header.hash()
            expected_height += 1
        return headers

    def compute_chain_work(self, headers: list[BlockHeaderV2]) -> int:
        return sum(work_for_target_v2(header.target) for header in headers)

    def _decode_header(self, header_bytes_hex: str) -> BlockHeaderV2:
        codec = BinaryCodec()
        raw = bytes.fromhex(header_bytes_hex)
        result = codec.decode_header_v2(raw)
        data = result[0] if isinstance(result, tuple) else result
        if not isinstance(data, dict):
            raise TypeError("decoded header is not a dict")
        return BlockHeaderV2.from_dict(data)


def header_hash(header: BlockHeaderV2) -> str:
    """Compute the canonical hash of a v2 header."""
    data = {
        "version": header.version,
        "prev_hash": header.prev_hash,
        "merkle_root": header.merkle_root,
        "registry_root": header.registry_root,
        "timestamp": header.timestamp,
        "target": f"{header.target:064x}",
        "nonce": header.nonce,
    }
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return HashEngine.hash_single_hex(raw)
