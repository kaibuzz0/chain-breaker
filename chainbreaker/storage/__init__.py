# chainbreaker.storage package
"""Durable storage subsystem for Chain-Breaker Protocol V2.

This package provides a storage backend boundary, journal-based atomic commits,
crash recovery, snapshots, indexes, and archive object storage. It deliberately
does not modify consensus rules or canonical serialization.
"""

from .backend import FlatFileStorageBackend, StorageBackend
from .formats import (
    decode_block_record,
    decode_head,
    decode_journal_record,
    encode_block_record,
    encode_head,
    encode_journal_record,
)
from .recovery import recover_store

__all__ = [
    "StorageBackend",
    "FlatFileStorageBackend",
    "encode_block_record",
    "decode_block_record",
    "encode_head",
    "decode_head",
    "encode_journal_record",
    "decode_journal_record",
    "recover_store",
]
