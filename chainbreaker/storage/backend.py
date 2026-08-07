"""Storage backend boundary and flat-file implementation."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from chainbreaker.block import BlockV2
from chainbreaker.codec import BinaryCodec
from chainbreaker.crypto import HashEngine
from chainbreaker.registry_state import (
    RegistryState,
    _txid_from_body,
    deserialize_registry_state,
    serialize_registry_state,
)

from .filesystem import (
    SingleWriterLock,
    StorageIOError,
    atomic_write,
    safe_unlink,
)
from .formats import (
    HEADER_LEN,
    JOURNAL_ABORT,
    JOURNAL_BEGIN,
    JOURNAL_COMMIT,
    decode_block_record,
    decode_head,
    encode_block_record,
    encode_head,
)
from .journal import Journal


class StorageBackend(ABC):
    """Abstract storage backend boundary."""

    @abstractmethod
    def get_tip(self) -> dict[str, Any]:
        """Return durable tip metadata (height, block_hash, ...)."""

    @abstractmethod
    def read_block(self, height: int) -> BlockV2:
        """Return the block at the given height."""

    @abstractmethod
    def read_header(self, height: int) -> bytes:
        """Return the exact 149-byte canonical Header V2."""

    @abstractmethod
    def append_block(self, block: BlockV2, previous_state: RegistryState) -> RegistryState:
        """Commit a validated block atomically and return the resulting registry state."""

    @abstractmethod
    def write_snapshot(self, height: int, state: RegistryState) -> None:
        """Persist a full registry snapshot."""

    @abstractmethod
    def read_snapshot(self, height: int) -> RegistryState | None:
        """Load a verified registry snapshot, or None."""

    @abstractmethod
    def put_archive_object(self, content_hash: str, data: bytes) -> None:
        """Persist a content-addressed archive object."""

    @abstractmethod
    def get_archive_object(self, content_hash: str) -> bytes:
        """Return archive object bytes by content hash."""

    @abstractmethod
    def close(self) -> None:
        """Release resources."""


class FlatFileStorageBackend(StorageBackend):
    """Flat-file storage backend with journal-based atomic commits."""

    STORAGE_FORMAT_VERSION = 1
    SNAPSHOT_INTERVAL = 100

    def __init__(
        self,
        chain_root: Path,
        network_id: str,
        genesis_hash: str,
        failpoint: Callable[[str], None] | None = None,
    ) -> None:
        self.chain_root = Path(chain_root)
        self.network_id = network_id
        self.genesis_hash = genesis_hash
        self.failpoint = failpoint or (lambda _name: None)

        self.lock = SingleWriterLock(self.chain_root / ".lock")
        self.lock.acquire()

        self._ensure_dirs()
        self.head_path = self.chain_root / "HEAD"
        self.journal_path = self.chain_root / "journal"
        self.config_path = self.chain_root / "config.json"
        self.tmp_dir = self.chain_root / "tmp"
        self.headers_dir = self.chain_root / "headers"
        self.blocks_dir = self.chain_root / "blocks"
        self.snapshots_dir = self.chain_root / "registry" / "snapshots"
        self.archive_dir = self.chain_root / "archive" / "objects"
        self.indexes_dir = self.chain_root / "indexes"

        self.journal = Journal(self.journal_path, failpoint=self.failpoint)
        self._write_config()

    def _ensure_dirs(self) -> None:
        for sub in [
            "tmp",
            "headers",
            "blocks",
            "registry/snapshots",
            "archive/objects",
            "indexes",
        ]:
            (self.chain_root / sub).mkdir(parents=True, exist_ok=True)

    def _write_config(self) -> None:
        if not self.config_path.exists():
            config = {
                "storage_format_version": self.STORAGE_FORMAT_VERSION,
                "network_id": self.network_id,
                "genesis_hash": self.genesis_hash,
                "backend": "flat-file",
            }
            atomic_write(self.config_path, json.dumps(config, sort_keys=True, indent=2).encode("utf-8"))

    def _block_path(self, height: int) -> Path:
        return self.blocks_dir / f"{height:010d}.bin"

    def _header_path(self, height: int) -> Path:
        return self.headers_dir / f"{height:010d}.hdr"

    def _snapshot_path(self, height: int) -> Path:
        return self.snapshots_dir / f"{height:010d}.state"

    def _archive_path(self, content_hash: str) -> Path:
        return self.archive_dir / content_hash[:2] / content_hash[2:4] / content_hash

    def _fail(self, name: str) -> None:
        self.failpoint(name)

    def get_tip(self) -> dict[str, Any]:

        if not self.head_path.exists():
            return {
                "height": 0,
                "block_hash": self.genesis_hash,
                "network_id": self.network_id,
                "genesis_hash": self.genesis_hash,
                "format_version": self.STORAGE_FORMAT_VERSION,
            }
        head_data: dict[str, Any] = decode_head(self.head_path.read_bytes())
        return head_data

    def read_header(self, height: int) -> bytes:
        path = self._header_path(height)
        if not path.exists():
            raise StorageIOError(f"missing header at height {height}")
        data = path.read_bytes()
        if len(data) != HEADER_LEN:
            raise StorageIOError(
                f"header at height {height} has {len(data)} bytes, expected {HEADER_LEN}"
            )
        return data

    def read_block(self, height: int) -> BlockV2:
        path = self._block_path(height)
        if not path.exists():
            raise StorageIOError(f"missing block at height {height}")
        data = path.read_bytes()
        block = decode_block_record(data)
        header_hash = HashEngine.hash_double_hex(self.read_header(height))
        if block.header.hash() != header_hash:
            raise StorageIOError(
                f"block at height {height} does not match stored header hash"
            )
        return block

    def append_block(
        self, block: BlockV2, previous_state: RegistryState
    ) -> RegistryState:
        """Atomically persist a validated block and advance HEAD."""
        from chainbreaker.governance import (
            CuratorRegisterTx,
            CuratorRevokeTx,
            CuratorRotateTx,
            GovernanceContext,
        )
        from chainbreaker.registry_state import apply_registry_transaction

        tip = self.get_tip()
        height = tip["height"] + 1
        if height <= 0:
            raise StorageIOError("cannot overwrite genesis via append_block")

        if height != tip["height"] + 1:
            raise StorageIOError(
                f"append_block height {height} does not follow tip {tip['height']}"
            )

        # Derive new registry state by replaying transactions.
        state = previous_state
        context = GovernanceContext(
            public_keys_hex=list(state.governance_keys),
            threshold=state.threshold,
        )
        for tx in block.transactions:
            body = tx.get("body", tx)
            tx_type = body.get("type")
            parsed: CuratorRegisterTx | CuratorRotateTx | CuratorRevokeTx | None = None
            if tx_type == "register":
                parsed = CuratorRegisterTx.from_dict(body)
            elif tx_type == "rotate":
                parsed = CuratorRotateTx.from_dict(body)
            elif tx_type == "revoke":
                parsed = CuratorRevokeTx.from_dict(body)
            else:
                continue
            txid = _txid_from_body(body)
            state = apply_registry_transaction(state, parsed, height, txid, context)

        block_hash = block.header.hash()

        # 1. BEGIN journal
        self._fail("before_begin")
        self.journal.append(JOURNAL_BEGIN, height)
        self._fail("after_begin")

        # 2. Stage artifacts
        header_bytes = BinaryCodec.encode_header_v2(block.header.to_dict())
        block_record = encode_block_record(block)
        snapshot_bytes = serialize_registry_state(state)

        self._fail("before_stage")
        tmp_header = self.tmp_dir / f"header.{height:010d}"
        tmp_block = self.tmp_dir / f"block.{height:010d}"
        tmp_snapshot = self.tmp_dir / f"state.{height:010d}"
        atomic_write(tmp_header, header_bytes)
        atomic_write(tmp_block, block_record)
        if height % self.SNAPSHOT_INTERVAL == 0:
            atomic_write(tmp_snapshot, snapshot_bytes)
        self._fail("after_stage")

        # 3. Verify staged hashes
        if HashEngine.hash_double_hex(header_bytes) != block_hash:
            self.journal.append(JOURNAL_ABORT, height, b"header hash mismatch")
            raise StorageIOError("staged header hash does not match block hash")

        # 4. Publish artifacts
        self._fail("before_publish")
        atomic_write(self._header_path(height), tmp_header.read_bytes())
        atomic_write(self._block_path(height), tmp_block.read_bytes())
        if (self.snapshots_dir / f"{height:010d}.state").exists() or height % self.SNAPSHOT_INTERVAL == 0:
            atomic_write(self._snapshot_path(height), snapshot_bytes)
        self._update_indexes(height, block_hash)
        self._fail("after_publish")

        # 5. COMMIT journal
        self.journal.append(JOURNAL_COMMIT, height)
        self._fail("after_commit")

        # 6. Update HEAD
        self._fail("before_head_update")
        atomic_write(
            self.head_path,
            encode_head(
                height,
                block_hash,
                self.network_id,
                self.genesis_hash,
                self.STORAGE_FORMAT_VERSION,
            ),
        )
        self._fail("after_head_update")

        # Clean up tmp files
        safe_unlink(tmp_header)
        safe_unlink(tmp_block)
        safe_unlink(tmp_snapshot)

        return state

    def _update_indexes(self, height: int, block_hash: str) -> None:
        height_to_hash = self._read_index_json(self.indexes_dir / "height_to_hash.json")
        hash_to_height = self._read_index_json(self.indexes_dir / "hash_to_height.json")
        height_to_hash[str(height)] = block_hash
        hash_to_height[block_hash] = height
        atomic_write(
            self.indexes_dir / "height_to_hash.json",
            json.dumps(height_to_hash, sort_keys=True, indent=2).encode("utf-8"),
        )
        atomic_write(
            self.indexes_dir / "hash_to_height.json",
            json.dumps(hash_to_height, sort_keys=True, indent=2).encode("utf-8"),
        )

    def _read_index_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return parsed

    def write_snapshot(self, height: int, state: RegistryState) -> None:
        data = serialize_registry_state(state)
        atomic_write(self._snapshot_path(height), data)
        meta = {
            "height": height,
            "network_id": self.network_id,
            "genesis_hash": self.genesis_hash,
            "registry_root": self._registry_root(state),
            "state_hash": HashEngine.hash_single_hex(data),
            "format_version": self.STORAGE_FORMAT_VERSION,
        }
        atomic_write(
            self._snapshot_path(height).with_suffix(".meta"),
            json.dumps(meta, sort_keys=True, indent=2).encode("utf-8"),
        )

    def _registry_root(self, state: RegistryState) -> str:
        from chainbreaker.registry_state import registry_root
        return registry_root(state)

    def read_snapshot(self, height: int) -> RegistryState | None:
        path = self._snapshot_path(height)
        if not path.exists():
            return None
        data = path.read_bytes()
        meta_path = path.with_suffix(".meta")
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("state_hash") != HashEngine.hash_single_hex(data):
                raise StorageIOError(f"snapshot at height {height} hash mismatch")
        return deserialize_registry_state(data)

    def put_archive_object(self, content_hash: str, data: bytes) -> None:
        if len(content_hash) != 64 or any(c not in "0123456789abcdef" for c in content_hash):
            raise ValueError("content_hash must be 64 lowercase hex chars")
        computed = HashEngine.hash_single_hex(data)
        if computed != content_hash:
            raise StorageIOError("archive object hash mismatch")
        path = self._archive_path(content_hash)
        if path.exists():
            existing = path.read_bytes()
            if existing != data:
                raise StorageIOError("archive object hash collision")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, data)

    def get_archive_object(self, content_hash: str) -> bytes:
        path = self._archive_path(content_hash)
        if not path.exists():
            raise StorageIOError(f"archive object not found: {content_hash}")
        data = path.read_bytes()
        if HashEngine.hash_single_hex(data) != content_hash:
            raise StorageIOError(f"archive object {content_hash} corrupt")
        return data

    def close(self) -> None:
        self.lock.release()
