"""Shared validation helpers for network payloads."""

from __future__ import annotations

import re

from .errors import NetworkValidationError

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_hex_hash(value: str) -> None:
    """Validate a 64-character lowercase hex string."""
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise NetworkValidationError(f"invalid hex hash: {value!r}")


def validate_nonnegative_int(value: object) -> None:
    """Validate that value is a non-negative integer."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise NetworkValidationError(f"expected non-negative int, got {value!r}")
