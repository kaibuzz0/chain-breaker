"""Write-ahead journal for storage commits."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any, Callable

from .filesystem import fsync_dir, fsync_file
from .formats import (
    decode_journal_record,
    encode_journal_record,
)


class JournalError(ValueError):
    """Raised when journal operations fail."""


class Journal:
    """Append-only write-ahead journal for atomic block commits."""

    def __init__(self, journal_path: Path, failpoint: Callable[[str], None] | None = None) -> None:
        self.journal_path = journal_path
        self.failpoint = failpoint
        self._seq = 0
        if self.journal_path.exists():
            self._seq = self._highest_seq()

    def _highest_seq(self) -> int:
        """Return the highest valid sequence number in the existing journal."""
        if not self.journal_path.exists():
            return 0
        data = self.journal_path.read_bytes()
        highest = 0
        offset = 0
        while offset < len(data):
            try:
                record, offset = decode_journal_record(data, offset)
                highest = max(highest, record["seq"])
            except ValueError:
                break
        return highest

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def append(self, record_type: int, height: int, payload: bytes = b"") -> None:
        """Append a journal record and flush."""
        self._invoke_failpoint("before_journal_append")
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = self._highest_seq()
        seq = self._next_seq()
        record = encode_journal_record(record_type, seq, height, payload)
        with open(self.journal_path, "ab") as fh:
            fh.write(record)
            fh.flush()
            os.fsync(fh.fileno())
        self._invoke_failpoint("after_journal_append")

    def _invoke_failpoint(self, name: str) -> None:
        if self.failpoint:
            self.failpoint(name)

    def read_records(self) -> list[dict[str, Any]]:
        """Read all valid journal records sequentially."""
        if not self.journal_path.exists():
            return []
        data = self.journal_path.read_bytes()
        records: list[dict[str, Any]] = []
        offset = 0
        while offset < len(data):
            try:
                record, next_offset = decode_journal_record(data, offset)
                records.append(record)
                offset = next_offset
            except ValueError:
                break
        return records

    def rotate(self, height: int) -> None:
        """Rotate the current journal to a height-suffixed archive."""
        if not self.journal_path.exists():
            return
        archive = self.journal_path.parent / f"journal.{height:020d}"
        if archive.exists():
            archive.unlink()
        self.journal_path.replace(archive)
        fsync_file(archive)
        fsync_dir(self.journal_path.parent)

    def reset(self) -> None:
        """Remove the journal. Used only in controlled recovery/test paths."""
        with contextlib.suppress(FileNotFoundError):
            self.journal_path.unlink()
