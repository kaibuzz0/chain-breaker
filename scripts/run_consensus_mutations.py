#!/usr/bin/env python3
"""Targeted consensus mutation campaign for Chain-Breaker Protocol V2."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGETS = {
    "chainbreaker/block.py": REPO / "chainbreaker" / "block.py",
    "chainbreaker/chain.py": REPO / "chainbreaker" / "chain.py",
    "chainbreaker/codec.py": REPO / "chainbreaker" / "codec.py",
    "chainbreaker/crypto.py": REPO / "chainbreaker" / "crypto.py",
    "chainbreaker/governance.py": REPO / "chainbreaker" / "governance.py",
    "chainbreaker/registry_state.py": REPO / "chainbreaker" / "registry_state.py",
    "chainbreaker/witness.py": REPO / "chainbreaker" / "witness.py",
}

MUTATIONS: list[tuple[str, str, str, str]] = [
    ("chainbreaker/block.py", "PoW <= to <", "return int(block_hash, 16) <= target", "return int(block_hash, 16) < target"),
    ("chainbreaker/block.py", "Genesis header length 149 to != 148", "if len(header_bytes) != 149:", "if len(header_bytes) != 148:"),
    ("chainbreaker/block.py", "Accept any version for genesis", "if header[\"version\"] != 2:", "if header[\"version\"] != 0:"),
    ("chainbreaker/block.py", "Allow prev_hash mismatch", "if header[\"prev_hash\"] != \"0\" * 64:", "if header[\"prev_hash\"] != \"1\" * 64:"),
    ("chainbreaker/block.py", "Allow target below MIN_TARGET", "if not (MIN_TARGET <= self.header.target <= MAX_TARGET):", "if not (0 <= self.header.target <= MAX_TARGET):"),
    ("chainbreaker/block.py", "Skip merkle root check", "if self.merkle_root() != self.header.merkle_root:", "if False:"),
    ("chainbreaker/chain.py", "Ignore previous hash link", "if block.header.prev_hash != expected_prev_hash:", "if False:"),
    ("chainbreaker/chain.py", "Ignore target expectation", "if block.header.target != expected_target:", "if False:"),
    ("chainbreaker/chain.py", "Ignore version enforcement", "if block.header.version != PROTOCOL_VERSION:", "if False:"),
    ("chainbreaker/chain.py", "Ignore registry root mismatch", "if block.header.registry_root != expected_registry_root:", "if False:"),
    ("chainbreaker/chain.py", "Disable canonical signature sorting", "canonical_body[\"governance_signatures\"] = sorted(\n            canonical_body[\"governance_signatures\"],\n            key=lambda s: int(s.get(\"key_index\", 0)),\n        )", "canonical_body[\"governance_signatures\"] = list(canonical_body[\"governance_signatures\"])"),
    ("chainbreaker/chain.py", "MTP <= to <", "if current.header.timestamp <= median:", "if current.header.timestamp < median:"),
    ("chainbreaker/codec.py", "Big-endian header encoding", "ENDIAN = \"<\"  # little-endian", "ENDIAN = \">\"  # big-endian"),
    ("chainbreaker/codec.py", "Accept wrong header type marker", "if data[offset] != cls.TYPE_HEADER:", "if False:"),
    ("chainbreaker/codec.py", "Allow short hashes", "if len(raw) != cls.HASH_LEN:", "if len(raw) > cls.HASH_LEN:"),
    ("chainbreaker/codec.py", "Allow non-canonical varints", "if cls._canonical_length(n) != 3:", "if False:"),
    ("chainbreaker/crypto.py", "SHA-256d to single SHA-256", "return hashlib.sha256(hashlib.sha256(data).digest()).digest()", "return hashlib.sha256(data).digest()"),
    ("chainbreaker/crypto.py", "Target conversion big to little endian", "return int.from_bytes(raw, \"big\")", "return int.from_bytes(raw, \"little\")"),
    ("chainbreaker/crypto.py", "Target encoding little to big endian", "return target.to_bytes(32, \"big\")", "return target.to_bytes(32, \"little\")"),
    ("chainbreaker/governance.py", "Threshold < to <=", "if valid < self.threshold:", "if valid <= self.threshold:"),
    ("chainbreaker/governance.py", "Allow duplicate key indices", "if sig.key_index in seen:", "if False:"),
    ("chainbreaker/governance.py", "Ignore wrong network_id", "if data.get(\"network_id\", NETWORK_ID) != NETWORK_ID:", "if False:"),
    ("chainbreaker/governance.py", "Ignore schema version", "if data.get(\"schema_version\", GOVERNANCE_SCHEMA_VERSION) != GOVERNANCE_SCHEMA_VERSION:", "if False:"),
    ("chainbreaker/governance.py", "Allow short signatures", "if len(sig_bytes) != 64:", "if len(sig_bytes) < 64:"),
    ("chainbreaker/registry_state.py", "Unsorted records in state root", "sorted_records = sorted(state.records, key=lambda r: r.curator_id.encode(\"utf-8\"))", "sorted_records = list(state.records)"),
    ("chainbreaker/registry_state.py", "Unsorted genesis keys", "sorted_keys = sorted(governance_keys)", "sorted_keys = list(governance_keys)"),
    ("chainbreaker/registry_state.py", "Registry root single SHA-256", "return HashEngine.hash_single_hex(serialize_registry_state(state))", "return HashEngine.hash_double_hex(serialize_registry_state(state))"),
    ("chainbreaker/registry_state.py", "Ignore previous_registry_root mismatch", "if tx.previous_registry_root != registry_root(state):", "if False:"),
    ("chainbreaker/registry_state.py", "Allow activation_height <= block_height", "if tx.activation_height <= block_height:", "if tx.activation_height < block_height:"),
    ("chainbreaker/registry_state.py", "Use current key instead of historical", "if record.public_key_hex == public_key_hex and record.is_active_at(height):", "if record.public_key_hex == public_key_hex:"),
    ("chainbreaker/witness.py", "Attestation V2 omit block_height", "\"block_height\": block_height,", ""),
    ("chainbreaker/witness.py", "Ignore witness height mismatch", "if witness_height != block_height:", "if False:"),
    ("chainbreaker/witness.py", "Attestation V2 version 2 to 1", "\"version\": 2,", "\"version\": 1,"),
]

OUTCOME_KILLED = "killed"
OUTCOME_SURVIVED = "survived"
OUTCOME_ERROR = "error"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_EXCLUDED = "excluded"
OUTCOME_EQUIVALENT = "equivalent"

def run_harness(work_dir: Path, timeout: int = 600) -> tuple[dict[str, str], dict[str, str]]:
    """Run pytest + vector validator + rust verifier. Return results and raw outputs."""
    results: dict[str, str] = {}
    outputs: dict[str, str] = {}
    env = os.environ.copy()
    env["PYTHONPATH"] = str(work_dir)

    pytest = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    results["pytest"] = "pass" if pytest.returncode == 0 else "fail"
    outputs["pytest"] = pytest.stdout + "\n" + pytest.stderr

    vec = subprocess.run(
        [sys.executable, "test-vectors/validate_vectors.py"],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    results["vectors_python"] = "pass" if vec.returncode == 0 else "fail"
    outputs["vectors_python"] = vec.stdout + "\n" + vec.stderr

    rust = subprocess.run(
        ["cargo", "run", "--manifest-path", "rust-verifier/Cargo.toml", "--", "verify", "test-vectors"],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=300,
    )
    results["vectors_rust"] = "pass" if (rust.returncode == 0 and "failed=0" in rust.stdout) else "fail"
    outputs["vectors_rust"] = rust.stdout + "\n" + rust.stderr
    return results, outputs

def apply_mutation(src: Path, dst: Path, old: str, new: str) -> bool:
    content = src.read_text(encoding="utf-8")
    if content.count(old) != 1:
        return False
    dst.write_text(content.replace(old, new, 1), encoding="utf-8")
    return True

def main() -> int:
    killed = 0
    survived = 0
    errors = 0
    timeouts = 0
    excluded = 0
    equivalent = 0
    records: list[dict[str, str]] = []
    start = time.monotonic()

    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / "chain-breaker"
        shutil.copytree(REPO, work, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "target"))

        for rel, description, old, new in MUTATIONS:
            src = REPO / rel
            dst = work / rel
            if not apply_mutation(src, dst, old, new):
                errors += 1
                records.append({"file": rel, "description": description, "outcome": OUTCOME_ERROR, "reason": "apply_failed"})
                print(f"[ERROR apply] {rel}: {description}")
                continue

            results = {}
            outputs = {}
            outcome = OUTCOME_KILLED
            reason = ""
            try:
                results, outputs = run_harness(work, timeout=600)
                if all(v == "pass" for v in results.values()):
                    outcome = OUTCOME_SURVIVED
                    reason = "all_harness_passed"
                    survived += 1
                    print(f"[SURVIVOR] {rel}: {description}")
                else:
                    outcome = OUTCOME_KILLED
                    reason = "harness_failure: " + ",".join(k for k, v in results.items() if v == "fail")
                    killed += 1
                    print(f"[KILLED] {rel}: {description} ({reason})")
            except subprocess.TimeoutExpired as exc:
                outcome = OUTCOME_TIMEOUT
                reason = str(exc)
                timeouts += 1
                print(f"[TIMEOUT] {rel}: {description}")
            except Exception as exc:
                outcome = OUTCOME_ERROR
                reason = f"{type(exc).__name__}: {exc}"
                errors += 1
                print(f"[ERROR run] {rel}: {description} ({reason})")

            records.append({
                "file": rel,
                "description": description,
                "outcome": outcome,
                "reason": reason,
                "results": results,
                "outputs": outputs,
            })

            # Restore original file for next mutation
            shutil.copy2(src, dst)

    elapsed = time.monotonic() - start
    executed = len(records)
    total = killed + survived + errors + timeouts + excluded + equivalent
    summary = {
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO), capture_output=True, text=True).stdout.strip(),
        "branch": subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(REPO), capture_output=True, text=True).stdout.strip(),
        "total_mutations": total,
        "executed": executed,
        "killed": killed,
        "survived": survived,
        "errors": errors,
        "timeouts": timeouts,
        "excluded": excluded,
        "equivalent": equivalent,
        "mutation_score": killed / executed if executed else 0.0,
        "runtime_seconds": elapsed,
        "records": records,
    }

    out = REPO / "docs" / "CONSENSUS_MUTATION_RESULTS.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary written to {out}")
    print(json.dumps({k: v for k, v in summary.items() if k != "records"}, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
