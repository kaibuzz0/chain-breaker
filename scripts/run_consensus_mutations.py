#!/usr/bin/env python3
"""Targeted consensus mutation campaign for Chain-Breaker Protocol V2.

This script applies a controlled set of mutations to copies of the
consensus-critical modules, runs the test/vector harness, and records which
mutations are killed and which survive.

It is intentionally lightweight and reviewable; it does not require a full
mutation-testing framework to be installed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGETS = [
    REPO / "chainbreaker" / "block.py",
    REPO / "chainbreaker" / "chain.py",
    REPO / "chainbreaker" / "codec.py",
    REPO / "chainbreaker" / "crypto.py",
    REPO / "chainbreaker" / "governance.py",
    REPO / "chainbreaker" / "registry_state.py",
    REPO / "chainbreaker" / "witness.py",
]

# Mutations are tuples of (description, old_text, new_text).
# They must be unique in the file they target.
MUTATIONS: list[tuple[Path, str, str, str]] = []

# Example mutation rules.  The full list is populated below from files that
# exist on disk so that the script can be inspected and extended without
# importing the modules.


def add_mutation(path: Path, description: str, old: str, new: str) -> None:
    MUTATIONS.append((path, description, old, new))


def run_harness(work_dir: Path) -> dict[str, str]:
    """Run pytest + vector validator + rust verifier, return pass/fail map."""
    results: dict[str, str] = {}

    # Run pytest (subset or full)
    pytest = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=600,
    )
    results["pytest"] = "pass" if pytest.returncode == 0 else "fail"

    # Run Python vector validator
    vec = subprocess.run(
        [sys.executable, "test-vectors/validate_vectors.py"],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    results["vectors_python"] = "pass" if vec.returncode == 0 else "fail"

    # Run Rust verifier if available
    rust = subprocess.run(
        ["cargo", "run", "--manifest-path", "rust-verifier/Cargo.toml", "--", "verify", "test-vectors"],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=300,
    )
    results["vectors_rust"] = "pass" if (rust.returncode == 0 and "failed=0" in rust.stdout) else "fail"

    return results


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
    survivors: list[dict[str, str]] = []

    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / "chain-breaker"
        shutil.copytree(REPO, work, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "target"))

        for src, description, old, new in MUTATIONS:
            rel = src.relative_to(REPO)
            dst = work / rel
            if not apply_mutation(src, dst, old, new):
                errors += 1
                print(f"[ERROR] could not apply mutation: {description} in {rel}")
                continue

            results = run_harness(work)
            killed_any = any(v == "fail" for v in results.values())

            if killed_any:
                killed += 1
                print(f"[KILLED] {rel}: {description}")
            else:
                survived += 1
                survivors.append({
                    "file": str(rel),
                    "description": description,
                    "old": old,
                    "new": new,
                })
                print(f"[SURVIVOR] {rel}: {description}")

            # Restore original file for next mutation
            shutil.copy2(src, dst)

    total = killed + survived + errors
    summary = {
        "total_mutations": total,
        "killed": killed,
        "survived": survived,
        "errors": errors,
        "mutation_score": killed / total if total else 0.0,
        "survivors": survivors,
    }

    out = REPO / "docs" / "CONSENSUS_MUTATION_RESULTS.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary written to {out}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
