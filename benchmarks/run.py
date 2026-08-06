
#!/usr/bin/env python3
"""Reproducible benchmark harness for Chain-Breaker v2.0.0-alpha."""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any

from chainbreaker.archive import Archive
from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block, mine_header_v2, satisfies_pow
from chainbreaker.codec import BinaryCodec
from chainbreaker.crypto import generate_keypair, encode_public_key, decode_private_key, sign, target_to_difficulty
from chainbreaker.governance import make_governance_signature, GovernanceSignature
from chainbreaker.registry_state import (
    RegistryState,
    GovernanceContext,
    CuratorRegisterTx,
    registry_root,
    apply_registry_transaction,
)
from chainbreaker.witness import sign_attestation_v2, verify_attestation_v2

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"

codec = BinaryCodec()


def _now() -> float:
    return time.perf_counter()


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    if len(values) == 1:
        return {"mean": values[0], "median": values[0], "min": values[0], "max": values[0], "stddev": 0.0}
    return {
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "stddev": statistics.stdev(values),
    }


def _write(result: dict[str, Any]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    suite = result["suite"]
    (RESULTS / f"{suite}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    latest = RESULTS / "latest.json"
    data = json.loads(latest.read_text(encoding="utf-8")) if latest.exists() else {}
    data[suite] = result
    latest.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _environment() -> dict[str, Any]:
    return {
        "os": platform.platform(),
        "python_version": platform.python_version(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "machine": platform.machine(),
        "commit": Path(__file__).resolve().parent.parent.joinpath(".git", "HEAD").read_text(encoding="utf-8").strip()
        if Path(__file__).resolve().parent.parent.joinpath(".git", "HEAD").exists()
        else None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def suite_sha256(iterations: int = 100_000) -> dict[str, Any]:
    header = create_genesis_block().header
    times = []
    for _ in range(iterations):
        t0 = _now()
        _ = codec.encode_header_v2(header.to_dict())
        times.append(_now() - t0)
    s = _stats(times)
    s["iterations"] = iterations
    s["throughput_per_second"] = iterations / s["mean"] if s["mean"] else 0.0
    s["suite"] = "sha256"
    s["environment"] = _environment()
    s["unit"] = "seconds per hash"
    return s


def suite_block_verify(iterations: int = 10_000) -> dict[str, Any]:
    block = create_genesis_block()
    times = []
    for _ in range(iterations):
        t0 = _now()
        _ = block.verify(allow_genesis=True)
        times.append(_now() - t0)
    s = _stats(times)
    s["iterations"] = iterations
    s["throughput_per_second"] = 1.0 / s["mean"] if s["mean"] else 0.0
    s["suite"] = "block_verify"
    s["environment"] = _environment()
    s["unit"] = "seconds per verification"
    return s


def suite_block_mine(iterations: int = 100) -> dict[str, Any]:
    template = create_genesis_block().header
    times = []
    for _ in range(iterations):
        header = BlockHeaderV2(
            version=template.version,
            prev_hash=template.hash(),
            merkle_root="0" * 64,
            registry_root=template.registry_root,
            timestamp=template.timestamp + 1,
            target=template.target,
            nonce=0,
        )
        t0 = _now()
        mine_header_v2(header, max_iterations=1_000_000)
        times.append(_now() - t0)
    s = _stats(times)
    s["iterations"] = iterations
    s["throughput_per_second"] = 1.0 / s["mean"] if s["mean"] else 0.0
    s["suite"] = "block_mine"
    s["environment"] = _environment()
    s["unit"] = "seconds per mine"
    s["note"] = "mining at genesis target"
    return s


def suite_ledger_replay(iterations: int = 10) -> dict[str, Any]:
    chain = [create_genesis_block()]
    template = chain[0].header
    for i in range(200):
        prev = chain[-1]
        header = BlockHeaderV2(
            version=template.version,
            prev_hash=prev.hash,
            merkle_root="0" * 64,
            registry_root=template.registry_root,
            timestamp=template.timestamp + i + 1,
            target=template.target,
            nonce=0,
        )
        mine_header_v2(header, max_iterations=1_000_000)
        chain.append(BlockV2(header=header, transactions=[]))
    times = []
    for _ in range(iterations):
        t0 = _now()
        for block in chain:
            _ = block.hash
        times.append(_now() - t0)
    s = _stats(times)
    s["iterations"] = iterations
    s["chain_length"] = len(chain)
    s["throughput_per_second"] = len(chain) / s["mean"] if s["mean"] else 0.0
    s["suite"] = "ledger_replay"
    s["environment"] = _environment()
    s["unit"] = "seconds to replay full chain"
    return s


def suite_registry_replay(iterations: int = 10) -> dict[str, Any]:
    sk, pk = generate_keypair()
    pk_hex = encode_public_key(pk)
    ctx = GovernanceContext([pk_hex], threshold=1)
    state = RegistryState.genesis([pk_hex], threshold=1)

    # Pre-build a chain of 100 valid register transactions, each signed against the prior state root.
    txs = []
    cur_state = state
    for i in range(100):
        prev_root = registry_root(cur_state)
        cur_sk, cur_pk = generate_keypair()
        cur_pk_hex = encode_public_key(cur_pk)
        body = {
            "action": "curator_register",
            "curator_id": f"curator_{i:04d}",
            "public_key_hex": cur_pk_hex,
            "activation_height": i + 2,
            "previous_registry_root": prev_root,
            "network_id": cur_state.network_id,
            "schema_version": cur_state.governance_version,
        }
        sig = make_governance_signature(sk, body, key_index=0)
        tx = CuratorRegisterTx(
            curator_id=f"curator_{i:04d}",
            public_key_hex=cur_pk_hex,
            activation_height=i + 2,
            display_metadata_hash=None,
            previous_registry_root=prev_root,
            governance_signatures=[sig],
            network_id=cur_state.network_id,
            schema_version=cur_state.governance_version,
        )
        txs.append(tx)
        cur_state = apply_registry_transaction(cur_state, tx, i + 1, f"{i:064x}", ctx)

    times = []
    for _ in range(iterations):
        replay_state = state
        t0 = _now()
        for i, tx in enumerate(txs):
            replay_state = apply_registry_transaction(replay_state, tx, i + 1, f"{i:064x}", ctx)
        times.append(_now() - t0)
    s = _stats(times)
    s["iterations"] = iterations
    s["registry_steps"] = len(txs)
    s["throughput_per_second"] = len(txs) / s["mean"] if s["mean"] else 0.0
    s["suite"] = "registry_replay"
    s["environment"] = _environment()
    s["unit"] = "seconds to replay registry transactions"
    return s


def suite_attest(iterations: int = 1_000) -> dict[str, Any]:
    genesis = create_genesis_block()
    sk, pk = generate_keypair()
    times_create = []
    times_verify = []
    attestations = []
    header_hash = genesis.header.hash()
    for _ in range(iterations):
        t0 = _now()
        att = sign_attestation_v2(sk, header_hash, "alpha", 0)
        times_create.append(_now() - t0)
        attestations.append(att)

    # Build a minimal registry state that considers curator alpha active at height 0.
    from chainbreaker.registry_state import RegistryState, CuratorRecord
    attest_state = RegistryState(
        records=(CuratorRecord(
            curator_id="alpha",
            public_key_hex=encode_public_key(pk),
            activation_height=0,
            revocation_height=None,
            previous_key_hex=None,
            registration_txid="0" * 64,
            latest_rotation_txid=None,
        ),),
        governance_version=1,
        network_id="chainbreaker-scripture-v2",
        governance_keys=(encode_public_key(pk),),
        threshold=1,
    )
    for att in attestations:
        t0 = _now()
        _ = verify_attestation_v2(attest_state, att, header_hash, 0)
        times_verify.append(_now() - t0)
    s_create = _stats(times_create)
    s_verify = _stats(times_verify)
    return {
        "suite": "attest",
        "iterations": iterations,
        "create": s_create,
        "verify": s_verify,
        "throughput_per_second": iterations / (s_create["mean"] + s_verify["mean"])
        if (s_create["mean"] + s_verify["mean"]) else 0.0,
        "environment": _environment(),
        "unit": "seconds per create+verify pair",
    }


def suite_archive_hash(iterations: int = 50) -> dict[str, Any]:
    times = []
    sizes_mb = [1, 10]
    with tempfile.TemporaryDirectory() as tmp:
        arc = Archive(str(tmp))
        for size_mb in sizes_mb:
            data = b"\x00" * (size_mb * 1024 * 1024)
            t0 = _now()
            for _ in range(iterations):
                _ = arc.add_document(data, title=f"blob_{size_mb}mb")
            elapsed = _now() - t0
            times.append(elapsed / iterations)
    s = _stats(times)
    s["iterations"] = iterations
    s["sizes_mb"] = sizes_mb
    s["throughput_per_second"] = 1.0 / s["mean"] if s["mean"] else 0.0
    s["suite"] = "archive_hash"
    s["environment"] = _environment()
    s["unit"] = "seconds per MB archive hash"
    return s


def suite_memory() -> dict[str, Any]:
    chain = [create_genesis_block()]
    template = chain[0].header
    for i in range(500):
        prev = chain[-1]
        header = BlockHeaderV2(
            version=template.version,
            prev_hash=prev.hash,
            merkle_root="0" * 64,
            registry_root=template.registry_root,
            timestamp=template.timestamp + i + 1,
            target=template.target,
            nonce=0,
        )
        mine_header_v2(header, max_iterations=1_000_000)
        chain.append(BlockV2(header=header, transactions=[]))
    tracemalloc.start()
    for block in chain:
        _ = block.hash
        _ = block.verify(allow_genesis=False)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "suite": "memory",
        "iterations": 1,
        "chain_length": len(chain),
        "current_memory_mb": current / (1024 * 1024),
        "peak_memory_mb": peak / (1024 * 1024),
        "environment": _environment(),
        "unit": "MB",
    }


def suite_startup() -> dict[str, Any]:
    # Measure import + genesis creation cold-start time
    times = []
    for _ in range(50):
        t0 = _now()
        # Local re-import to avoid module caching effects is hard; instead measure repeated genesis creation
        _ = create_genesis_block()
        times.append(_now() - t0)
    s = _stats(times)
    s["iterations"] = len(times)
    s["throughput_per_second"] = 1.0 / s["mean"] if s["mean"] else 0.0
    s["suite"] = "startup"
    s["environment"] = _environment()
    s["unit"] = "seconds to create genesis block"
    return s


SUITES = {
    "sha256": suite_sha256,
    "block_verify": suite_block_verify,
    "block_mine": suite_block_mine,
    "ledger_replay": suite_ledger_replay,
    "registry_replay": suite_registry_replay,
    "attest": suite_attest,
    "archive_hash": suite_archive_hash,
    "memory": suite_memory,
    "startup": suite_startup,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Chain-Breaker v2.0.0-alpha benchmark harness")
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
        _write(result)
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
