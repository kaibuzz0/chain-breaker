"""Deterministic crash recovery for flat-file storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chainbreaker.crypto import HashEngine

from .filesystem import atomic_write, safe_unlink
from .formats import (
    HEADER_LEN,
    JOURNAL_COMMIT,
    decode_block_record,
    decode_head,
    decode_journal_record,
)


class RecoveryError(ValueError):
    """Raised when recovery cannot determine a safe durable height."""


def _path_height(path: Path) -> int:
    """Return integer height from a filename like '0000000005.bin'."""
    return int(path.stem)


def _scan_height_files(directory: Path, suffix: str) -> set[int]:
    return {_path_height(p) for p in directory.glob(f"*{suffix}") if p.is_file()}


def _read_last_commit_height(journal_path: Path) -> int:
    """Return the height of the last valid COMMIT record, or 0."""
    if not journal_path.exists():
        return 0
    data = journal_path.read_bytes()
    highest = 0
    offset = 0
    while offset < len(data):
        try:
            record, offset = decode_journal_record(data, offset)
            if record["type"] == JOURNAL_COMMIT and record["height"] > highest:
                highest = record["height"]
        except ValueError:
            break
    return highest


def _verify_block_at_height(chain_root: Path, height: int, expected_hash: str) -> bool:
    """Verify header and block at height match expected_hash."""
    header_path = chain_root / "headers" / f"{height:010d}.hdr"
    block_path = chain_root / "blocks" / f"{height:010d}.bin"
    if not header_path.exists() or not block_path.exists():
        return False
    header_data = header_path.read_bytes()
    if len(header_data) != HEADER_LEN:
        return False
    if HashEngine.hash_double_hex(header_data) != expected_hash:
        return False
    try:
        block = decode_block_record(block_path.read_bytes())
    except ValueError:
        return False
    return block.header.hash() == expected_hash


def recover_store(
    chain_root: Path,
    network_id: str,
    genesis_hash: str,
    max_height: int | None = None,
) -> dict[str, Any]:
    """Recover the safe durable tip after an unclean shutdown.

    Returns dict with keys:
      height, block_hash, network_id, genesis_hash, format_version,
      rolled_back_heights, rebuilt_indexes, recovery_note.
    """
    chain_root = Path(chain_root)
    head_path = chain_root / "HEAD"
    journal_path = chain_root / "journal"
    headers_dir = chain_root / "headers"
    blocks_dir = chain_root / "blocks"

    head_height = 0
    head_hash = genesis_hash
    if head_path.exists():
        try:
            head = decode_head(head_path.read_bytes())
            head_height = head["height"]
            head_hash = head["block_hash"]
            if head["genesis_hash"] != genesis_hash:
                raise RecoveryError("HEAD genesis hash mismatch")
        except ValueError:
            head_height = 0
            head_hash = genesis_hash

    commit_height = _read_last_commit_height(journal_path)
    safe_height = min(head_height, commit_height)
    if max_height is not None and safe_height > max_height:
        safe_height = max_height

    # Walk backward from safe_height, verifying each block links to current_hash.
    rolled_back: list[int] = []
    current_hash = head_hash
    for h in range(safe_height, 0, -1):
        if _verify_block_at_height(chain_root, h, current_hash):
            try:
                block = decode_block_record((blocks_dir / f"{h:010d}.bin").read_bytes())
                current_hash = block.header.prev_hash
            except ValueError:
                rolled_back.append(h)
                current_hash = genesis_hash
                safe_height = h - 1
                break
        else:
            rolled_back.append(h)
            current_hash = genesis_hash
            safe_height = h - 1
            break

    # Delete artifacts above safe_height
    for h in _scan_height_files(headers_dir, ".hdr"):
        if h > safe_height:
            safe_unlink(headers_dir / f"{h:010d}.hdr")
    for h in _scan_height_files(blocks_dir, ".bin"):
        if h > safe_height:
            safe_unlink(blocks_dir / f"{h:010d}.bin")
    for snapshot in (chain_root / "registry" / "snapshots").glob("*.state"):
        h = _path_height(snapshot)
        if h > safe_height:
            safe_unlink(snapshot)
            safe_unlink(snapshot.with_suffix(".meta"))

    # Rewrite HEAD if needed
    if safe_height != head_height:
        atomic_write(
            head_path,
            f"{safe_height:020d}:{current_hash}:{network_id}:{genesis_hash}:1\n".encode(),
        )

    # Rebuild indexes from canonical data
    height_to_hash: dict[str, str] = {}
    hash_to_height: dict[str, int] = {}
    for h in sorted(_scan_height_files(blocks_dir, ".bin")):
        if h > safe_height:
            continue
        block_path = blocks_dir / f"{h:010d}.bin"
        try:
            block = decode_block_record(block_path.read_bytes())
            bh = block.header.hash()
            height_to_hash[str(h)] = bh
            hash_to_height[bh] = h
        except ValueError:
            continue

    indexes_dir = chain_root / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    if height_to_hash:
        atomic_write(
            indexes_dir / "height_to_hash.json",
            json.dumps(height_to_hash, sort_keys=True, indent=2).encode("utf-8"),
        )
        atomic_write(
            indexes_dir / "hash_to_height.json",
            json.dumps(hash_to_height, sort_keys=True, indent=2).encode("utf-8"),
        )

    note = "clean recovery" if not rolled_back else f"rolled back heights {rolled_back}"
    return {
        "height": safe_height,
        "block_hash": current_hash,
        "network_id": network_id,
        "genesis_hash": genesis_hash,
        "format_version": 1,
        "rolled_back_heights": rolled_back,
        "rebuilt_indexes": list(height_to_hash.keys()),
        "recovery_note": note,
    }
