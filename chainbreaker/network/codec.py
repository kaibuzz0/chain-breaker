"""Canonical JSON codec for network message payloads."""

from __future__ import annotations

import json
from typing import Any


def encode_payload(obj: Any) -> bytes:
    """Encode a typed payload to canonical JSON bytes."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def decode_payload(payload: bytes) -> Any:
    """Decode canonical JSON payload bytes."""
    return json.loads(payload.decode("utf-8"))
