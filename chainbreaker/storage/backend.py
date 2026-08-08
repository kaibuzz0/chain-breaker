"""Storage backend boundary and flat-file implementation."""

from __future__ import annotations

import json
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

from .filesystem import SingleWriterLock, StorageIOError, atomic_write, fsync_dir, safe_unlink
from .formats import (
    JOURNAL_ABORT,
    JOURNAL_BEGIN,
    JOURNAL_BLOCK_STAGED,
    JOURNAL_COMMIT,
    JOURNAL_HEADER_STAGED,
    JOURNAL_INDEX_STAGED,
    JOURNAL_REGISTRY_STAGED,
    encode_block_record,
    encode_head,
)
from .journal import Journal


class StorageBackend:
    """Abstract storage backend boundary."""

    def get_tip(self) -> dict[str, Any]:
        raise NotImplementedError

    def read_header(self, height: int) -> bytes:
        raise NotImplementedError

    def read_block(self, height: int) -> BlockV2:
        raise NotImplementedError

    def append_block(self, block: BlockV2, previous_state: RegistryState) -> RegistryState:
        raise NotImplementedError

    def write_snapshot(self, height: int, state: RegistryState) -> None:
        raise NotImplementedError

    def read_snapshot(self, height: int) -> RegistryState | None:
        raise NotImplementedError

    def put_archive_object(self, content_hash: str, data: bytes) -> None:
        raise NotImplementedError

    def get_archive_object(self, content_hash: str) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def read_chain_up_to(self, height: int) -> list[BlockV2]:
        """Read the canonical chain from genesis up to the given height."""
        raise NotImplementedError

    def list_blocks(self) -> list[int]:
        """Return sorted list of canonical block heights present on disk."""
        raise NotImplementedError

    def atomic_tip_switch(
        self,
        new_tip_height: int,
        new_tip_hash: str,
        disconnect_heights: list[int] | None = None,
    ) -> dict[str, Any]:
        """Atomically update HEAD to the new tip and rebuild derived data."""
        raise NotImplementedError

    def rebuild_indexes(self) -> dict[str, Any]:
        """Rebuild all derived indexes from canonical block files."""
        raise NotImplementedError


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

    def _fail(self, name: str) -> None:
        self.failpoint(name)

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
        prefix1 = content_hash[:2]
        prefix2 = content_hash[2:4]
        return self.archive_dir / prefix1 / prefix2 / content_hash

    def get_tip(self) -> dict[str, Any]:
        from .formats import decode_head
        if not self.head_path.exists():
            result: dict[str, Any] = {
                "height": 0,
                "block_hash": self.genesis_hash,
                "network_id": self.network_id,
                "genesis_hash": self.genesis_hash,
                "format_version": self.STORAGE_FORMAT_VERSION,
            }
            return result
        result = decode_head(self.head_path.read_bytes())
        return result

    def read_header(self, height: int) -> bytes:
        from .formats import HEADER_LEN
        path = self._header_path(height)
        if not path.exists():
            raise StorageIOError(f"header not found at height {height}")
        data = path.read_bytes()
        if len(data) != HEADER_LEN:
            raise StorageIOError(f"header at height {height} has wrong length: {len(data)}")
        return data

    def read_block(self, height: int) -> BlockV2:
        from .formats import decode_block_record
        path = self._block_path(height)
        if not path.exists():
            raise StorageIOError(f"block not found at height {height}")
        return decode_block_record(path.read_bytes())

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

        # 2. Stage header
        header_bytes = BinaryCodec.encode_header_v2(block.header.to_dict())
        self._fail("before_header_stage")
        tmp_header = self.tmp_dir / f"header.{height:010d}"
        atomic_write(tmp_header, header_bytes)
        self._fail("after_header_stage")
        self.journal.append(JOURNAL_HEADER_STAGED, height, header_bytes)
        self._fail("after_header_staged_record")

        # 3. Stage block record
        block_record = encode_block_record(block)
        self._fail("before_block_stage")
        tmp_block = self.tmp_dir / f"block.{height:010d}"
        atomic_write(tmp_block, block_record)
        self._fail("after_block_stage")
        self.journal.append(JOURNAL_BLOCK_STAGED, height, block_record)
        self._fail("after_block_staged_record")

        # 4. Stage snapshot
        snapshot_bytes = serialize_registry_state(state)
        self._fail("before_registry_stage")
        tmp_snapshot = self.tmp_dir / f"state.{height:010d}"
        atomic_write(tmp_snapshot, snapshot_bytes)
        self._fail("after_registry_stage")
        self.journal.append(JOURNAL_REGISTRY_STAGED, height, snapshot_bytes)
        self._fail("after_registry_staged_record")

        # 5. Verify staged hashes
        if HashEngine.hash_double_hex(header_bytes) != block_hash:
            self.journal.append(JOURNAL_ABORT, height, b"header hash mismatch")
            raise StorageIOError("staged header hash does not match block hash")

        # 6. Publish artifacts
        self._fail("before_publish")
        self._fail("during_header_rename")
        atomic_write(self._header_path(height), tmp_header.read_bytes())
        self._fail("after_header_publish")
        self._fail("during_block_rename")
        atomic_write(self._block_path(height), tmp_block.read_bytes())
        self._fail("after_block_publish")
        if (self.snapshots_dir / f"{height:010d}.state").exists() or height % self.SNAPSHOT_INTERVAL == 0:
            atomic_write(self._snapshot_path(height), snapshot_bytes)
        self._fail("after_snapshot_publish")
        self._fail("before_index_stage")
        self._update_indexes(height, block_hash)
        self.journal.append(JOURNAL_INDEX_STAGED, height)
        self._fail("after_index_stage")
        self._fail("after_publish")

        # 7. fsync durability boundary
        self._fail("before_fsync")
        fsync_dir(self.headers_dir)
        fsync_dir(self.blocks_dir)
        fsync_dir(self.snapshots_dir)
        fsync_dir(self.indexes_dir)
        self._fail("after_fsync")

        # 8. COMMIT journal
        self._fail("before_commit")
        self.journal.append(JOURNAL_COMMIT, height)
        self._fail("during_commit")
        self._fail("after_commit")

        # 9. Update HEAD
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

        # 10. Directory sync
        self._fail("before_dir_sync")
        fsync_dir(self.chain_root)
        self._fail("after_dir_sync")

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
        # Snapshots above the canonical HEAD belong to an orphaned or future
        # branch and must not be trusted as canonical state.
        tip = self.get_tip()
        if height > tip["height"]:
            return None
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

    def read_chain_up_to(self, height: int) -> list[BlockV2]:
        """Read canonical blocks from genesis up to and including height."""
        blocks: list[BlockV2] = []
        for h in range(0, height + 1):
            if h == 0:
                from chainbreaker.block import create_genesis_block

                genesis = create_genesis_block(network_id=self.network_id)
                blocks.append(genesis)
                continue
            try:
                blocks.append(self.read_block(h))
            except Exception as exc:
                raise StorageIOError(f"cannot read canonical block at height {h}: {exc}") from exc
        return blocks

    def list_blocks(self) -> list[int]:
        """Return sorted canonical block heights."""
        heights = []
        for p in self.blocks_dir.glob("*.bin"):
            try:
                heights.append(int(p.stem))
            except ValueError:
                continue
        return sorted(heights)

    def atomic_tip_switch(
        self,
        new_tip_height: int,
        new_tip_hash: str,
        disconnect_heights: list[int] | None = None,
    ) -> dict[str, Any]:
        """Atomically update HEAD and rebuild derived indexes.

        Durability ordering: journal commit record is durable before HEAD is
        rewritten, so a crash after HEAD update can still recover to the new
        tip by replaying the journal.
        """
        if new_tip_height < 0:
            raise StorageIOError("tip height must be non-negative")

        self._fail("before_reorg_commit")
        self.journal.append(JOURNAL_COMMIT, new_tip_height)
        self._fail("after_reorg_commit")

        self._fail("before_head_update")
        head_line = (
            f"{new_tip_height:020d}:{new_tip_hash}:"
            + f"{self.network_id}:{self.genesis_hash}:{self.STORAGE_FORMAT_VERSION}"
            + chr(10)
        )
        atomic_write(self.head_path, head_line.encode("utf-8"))
        self._fail("after_head_update")

        index_info = self.rebuild_indexes()

        return {
            "new_tip_height": new_tip_height,
            "new_tip_hash": new_tip_hash,
            "rebuilt_indexes": index_info,
        }

    def rebuild_indexes(self) -> dict[str, Any]:
        """Rebuild height/hash indexes from canonical block files below HEAD."""
        tip = self.get_tip()
        safe_height = tip["height"]
        height_to_hash: dict[str, str] = {}
        hash_to_height: dict[str, int] = {}
        for h in self.list_blocks():
            if h > safe_height:
                continue
            try:
                block = self.read_block(h)
                bh = block.header.hash()
                height_to_hash[str(h)] = bh
                hash_to_height[bh] = h
            except (StorageIOError, FileNotFoundError, ValueError):
                # A missing or corrupt block below the tip is left out of the
                # rebuilt indexes; the HEAD/verification path is authoritative.
                continue

        self.indexes_dir.mkdir(parents=True, exist_ok=True)
        if height_to_hash:
            atomic_write(
                self.indexes_dir / "height_to_hash.json",
                json.dumps(height_to_hash, sort_keys=True, indent=2).encode("utf-8"),
            )
            atomic_write(
                self.indexes_dir / "hash_to_height.json",
                json.dumps(hash_to_height, sort_keys=True, indent=2).encode("utf-8"),
            )
        else:
            for name in ("height_to_hash.json", "hash_to_height.json"):
                ip = self.indexes_dir / name
                if ip.exists():
                    safe_unlink(ip)

        return {
            "tip_height": safe_height,
            "indexed_heights": sorted(int(k) for k in height_to_hash),
        }

    def close(self) -> None:
        self.lock.release()
