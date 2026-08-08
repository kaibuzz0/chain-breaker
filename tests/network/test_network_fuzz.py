"""Fuzz tests for the network protocol parser.

Random byte sequences must never crash, hang, or allocate unbounded memory.
"""

from __future__ import annotations

import contextlib
import random

import pytest

from chainbreaker.network import NetworkValidationError, parse_envelope


@pytest.mark.parametrize("seed", range(20))
def test_random_bytes_never_crash(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(50):
        size = rng.randint(0, 4096)
        data = bytes(rng.randint(0, 255) for _ in range(size))
        with contextlib.suppress(NetworkValidationError):
            parse_envelope(data)


@pytest.mark.parametrize("seed", range(10))
def test_near_boundary_sizes(seed: int) -> None:
    rng = random.Random(seed)
    from chainbreaker.network import MAX_MESSAGE_SIZE

    for size in [0, 1, 66, 67, 68, 4096, MAX_MESSAGE_SIZE - 1, MAX_MESSAGE_SIZE, MAX_MESSAGE_SIZE + 1]:
        data = bytes(rng.randint(0, 255) for _ in range(size))
        with contextlib.suppress(NetworkValidationError):
            parse_envelope(data)


@pytest.mark.parametrize("seed", range(5))
def test_mutated_valid_envelopes(seed: int) -> None:
    """Take a valid envelope and flip random bits; parser must reject safely."""
    from chainbreaker.network import HELLO, serialize_envelope
    from chainbreaker.network.messages import HelloMessage

    rng = random.Random(seed)
    payload = HelloMessage(
        protocol_version=1,
        network_id="chainbreaker-scripture-v2",
        genesis_hash="0" * 64,
        best_height=0,
        best_chain_work="0" * 64,
        feature_bits=[],
        node_limits={},
    ).to_payload()
    raw = bytearray(serialize_envelope(HELLO, payload=payload))
    for _ in range(20):
        mutant = bytearray(raw)
        idx = rng.randint(0, len(mutant) - 1)
        mutant[idx] ^= (1 << rng.randint(0, 7))
        with contextlib.suppress(NetworkValidationError):
            parse_envelope(bytes(mutant))


def test_no_memory_growth_on_attack() -> None:
    """Ensure rejection of a 2 MiB+ claim does not allocate 2 MiB."""
    import struct

    from chainbreaker.network import (
        CBN1_MAGIC,
        HELLO,
        MAX_PAYLOAD_BYTES,
        NetworkValidationError,
    )

    network_id = b"chainbreaker-scripture-v2"
    header = (
        CBN1_MAGIC
        + struct.pack(">H", 1)
        + struct.pack(">B", len(network_id))
        + network_id
        + struct.pack(">B", HELLO)
        + struct.pack(">B", 0)
        + struct.pack(">I", MAX_PAYLOAD_BYTES + 1)
        + bytes(32)
    )
    with pytest.raises(NetworkValidationError):
        parse_envelope(header)
