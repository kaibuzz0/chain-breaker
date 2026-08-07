"""Single-writer lock tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreaker.storage import FlatFileStorageBackend
from chainbreaker.storage.filesystem import SingleWriterLock, StorageIOError


def test_second_backend_fails_to_lock(tmp_path: Path):
    root = tmp_path / "chain"
    backend1 = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash="0" * 64,
    )
    try:
        with pytest.raises(StorageIOError):
            FlatFileStorageBackend(
                chain_root=root,
                network_id="test-net",
                genesis_hash="0" * 64,
            )
    finally:
        backend1.close()


def test_lock_released_on_close_then_reacquired(tmp_path: Path):
    root = tmp_path / "chain"
    backend = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash="0" * 64,
    )
    backend.close()
    backend2 = FlatFileStorageBackend(
        chain_root=root,
        network_id="test-net",
        genesis_hash="0" * 64,
    )
    backend2.close()


def test_stale_lock_detected_after_owner_death(tmp_path: Path):
    lock_path = tmp_path / ".lock"
    lock_path.write_text("999999\n")
    lock = SingleWriterLock(lock_path)
    lock.acquire()
    lock.release()
