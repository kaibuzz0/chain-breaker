"""Filesystem primitives for durable storage.

Handles atomic file writes, directory flushing where supported, and a simple
process-level single-writer lock.
"""

from __future__ import annotations

import contextlib
import errno
import os
import platform
import tempfile
from pathlib import Path
from typing import Any


class StorageIOError(OSError):
    """Raised when a storage operation cannot achieve the requested durability."""


_FSYNC_DIR_SUPPORTED = platform.system() != "Windows"


def fsync_file(path: Path) -> None:
    """Flush file contents to stable storage."""
    with open(path, "rb+") as fh:
        fh.flush()
        os.fsync(fh.fileno())


def fsync_dir(path: Path) -> None:
    """Flush directory metadata if the platform supports it."""
    if not _FSYNC_DIR_SUPPORTED:
        return
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes) -> None:
    """Atomically write data to path via a temporary file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
    finally:
        fsync_dir(path.parent)


def safe_unlink(path: Path) -> None:
    """Remove a file, ignoring ENOENT."""
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def list_files(path: Path) -> list[Path]:
    """Return sorted list of files in a directory."""
    if not path.exists():
        return []
    return sorted(p for p in path.iterdir() if p.is_file())


class SingleWriterLock:
    """A simple process-level single-writer lock file.

    The lock file contains the current PID and an identifier. It is advisory:
    all writers must use the same lock path. Stale lock detection is
    conservative: a lock is considered stale only if the recorded PID is not
    alive on the same machine. This is not a security primitive.
    """

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            content = self.lock_path.read_text(encoding="utf-8")
            try:
                pid = int(content.strip().split()[0])
            except (ValueError, IndexError):
                pid = None
            if pid is not None and _pid_alive(pid):
                raise StorageIOError(f"storage lock held by process {pid}")
            safe_unlink(self.lock_path)
        tmp = self.lock_path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(f"{os.getpid()} {platform.node()}\n", encoding="utf-8")
        try:
            os.replace(str(tmp), str(self.lock_path))
        except OSError:
            safe_unlink(tmp)
            raise

    def release(self) -> None:
        safe_unlink(self.lock_path)

    def __enter__(self) -> SingleWriterLock:
        self.acquire()
        return self

    def __exit__(self, *args: Any) -> None:
        self.release()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        return exc.errno == errno.EPERM
    return True
