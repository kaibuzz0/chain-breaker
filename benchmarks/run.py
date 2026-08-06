#!/usr/bin/env python3
"""Reproducible benchmark harness for Chain-Breaker."""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

from chainbreaker.archive import load_block
from chainbreaker.block import Block, Header, make_genesis_block
from chainbreaker.codec import encode_header, hash_bytes
from chainbreaker.consensus import validate_block
from chainbreaker.registry_state import replay_registry
from chainbreaker.witness import create_attestation, verify_attestation

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def _now() -> float:
    return time.perf_counter()


def _mean_stddev(values: list[float]) -> tuple[float, float]:
    if len(values) < 2:
        return values[0], 0.0
    return statistics.mean(values), statistics.stdev(values)


def _record(result: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    suite = result["suite"]
    (RESULTS / f"{suite}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    latest = RESULTS / "latest.json"
    if latest.exists():
        data = json.loads(latest.read_text(encoding="utf-8"))
    else:
        data = {}
    data[suite] = result
    latest.write_text(json.dumps(data, indent=2), encoding="utf-8")


def suite_hash(iterations: int = 100_000) -> dict:
    header = make_genesis_block([b"test"]).header
    start = _now()
    for _ in range(iterations):
        encode_header(header)
    elapsed = _now() - start
    return {
        "suite": "hash",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "iterations": iterations,
        "mean_seconds": elapsed / iterations,
        "throughput_per_second": iterations / elapsed if elapsed else 0.0,
    }


def suite_block(iterations: int = 100) -> dict:
    block = make_genesis_block([b"test"])
    times = []
    for _ in range(iterations):
        t0 = _now()
        validate_block(block)
        times.append(_now() - t0)
    mean, stddev = _mean_stddev(times)
    return {
        "suite": "block",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "iterations": iterations,
        "mean_seconds": mean,
        "stddev_seconds": stddev,
        "throughput_per_second": 1.0 / mean if mean else 0.0,
    }


def suite_replay(iterations: int = 10) -> dict:
    # Build a minimal chain in memory
    from chainbreaker.crypto import generate_keypair
    from chainbreaker.registry_state import apply_action, make_genesis_registry
    from chainbreaker.governance import make_register_action

    sk, pk = generate_keypair()
    registry = make_genesis_registry([pk])
    block = make_genesis_block([b"alpha"])
    chain = [block]
    for i in range(50):
        prev = chain[-1]
        new_header = Header(
            version=prev.header.version,
            height=prev.header.height + 1,
            timestamp=prev.header.timestamp + 1,
            prev_hash=prev.header.hash,
            registry_root=registry.root_hash,
            nonce=0,
            difficulty=prev.header.difficulty,
            actions=[],
        )
        chain.append(Block(header=new_header, actions=[]))
    times = []
    for _ in range(iterations):
        t0 = _now()
        list(replay_registry(chain))
        times.append(_now() - t0)
    mean, stddev = _mean_stddev(times)
    return {
        "suite": "replay",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "iterations": iterations,
        "mean_seconds": mean,
        "stddev_seconds": stddev,
        "throughput_per_second": len(chain) / mean if mean else 0.0,
    }


def suite_attest(iterations: int = 1_000) -> dict:
    from chainbreaker.crypto import generate_keypair
    block = make_genesis_block([b"test"])
    sk, pk = generate_keypair()
    times_create = []
    times_verify = []
    attestations = []
    for _ in range(iterations):
        t0 = _now()
        att = create_attestation(block.header, 0, sk)
        times_create.append(_now() - t0)
        attestations.append(att)
    for att in attestations:
        t0 = _now()
        verify_attestation(att, block.header, [pk])
        times_verify.append(_now() - t0)
    mean_create, std_create = _mean_stddev(times_create)
    mean_verify, std_verify = _mean_stddev(times_verify)
    return {
        "suite": "attest",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "iterations": iterations,
        "mean_create_seconds": mean_create,
        "stddev_create_seconds": std_create,
        "mean_verify_seconds": mean_verify,
        "stddev_verify_seconds": std_verify,
        "throughput_per_second": iterations / (mean_create + mean_verify) if (mean_create + mean_verify) else 0.0,
    }


def suite_archive(iterations: int = 100) -> dict:
    from chainbreaker.archive import archive_file
    times = []
    for size_mb in [1]:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"0" * (size_mb * 1024 * 1024))
            path = Path(f.name)
        try:
            t0 = _now()
            for _ in range(iterations):
                archive_file(path)
            times.append((_now() - t0) / iterations)
        finally:
            path.unlink(missing_ok=True)
    mean = statistics.mean(times)
    return {
        "suite": "archive",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "iterations": iterations,
        "mean_seconds": mean,
        "throughput_per_second": 1.0 / mean if mean else 0.0,
    }


def suite_memory() -> dict:
    import tracemalloc
    from chainbreaker.crypto import generate_keypair
    from chainbreaker.registry_state import make_genesis_registry
    pk = generate_keypair()[1]
    registry = make_genesis_registry([pk])
    block = make_genesis_block([b"alpha"])
    chain = [block]
    for i in range(200):
        prev = chain[-1]
        chain.append(Block(
            header=Header(
                version=prev.header.version,
                height=prev.header.height + 1,
                timestamp=prev.header.timestamp + 1,
                prev_hash=prev.header.hash,
                registry_root=registry.root_hash,
                nonce=0,
                difficulty=prev.header.difficulty,
                actions=[],
            ),
            actions=[],
        ))
    tracemalloc.start()
    list(replay_registry(chain))
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "suite": "memory",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "iterations": 1,
        "current_memory_mb": current / (1024 * 1024),
        "peak_memory_mb": peak / (1024 * 1024),
    }


SUITES = {
    "hash": suite_hash,
    "block": suite_block,
    "replay": suite_replay,
    "attest": suite_attest,
    "archive": suite_archive,
    "memory": suite_memory,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Chain-Breaker benchmark harness")
    parser.add_argument("--suite", choices=list(SUITES.keys()) + ["all"], default="all")
    parser.add_argument("--iterations", type=int, default=None)
    args = parser.parse_args()

    suites = list(SUITES.keys()) if args.suite == "all" else [args.suite]
    for name in suites:
        fn = SUITES[name]
        kwargs = {}
        if name != "memory" and args.iterations is not None:
            kwargs["iterations"] = args.iterations
        result = fn(**kwargs)
        result["peak_memory_mb"] = None  # placeholder for future instrumentation
        _record(result)
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
