# 8M-D: Independent Python/Rust network identity verification expansion.
"""The Rust verifier must independently derive the same values from the same inputs.

This file tests that the Python side produces deterministic, frozen vector values
and that the vector generator is idempotent.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_network_identity_vector_file_exists():
    assert (REPO / "test-vectors" / "network-identities.json").exists()
    assert (REPO / "test-vectors" / "network-identities-test-genesis.bin").exists()
    assert (REPO / "test-vectors" / "network-identities-test-genesis.hash").exists()


def test_network_identity_vector_generator_is_idempotent():
    import subprocess
    import sys

    vector_path = REPO / "test-vectors" / "network-identities.json"
    original = vector_path.read_text(encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(REPO / "test-vectors" / "generate_network_identity_vectors.py")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    regenerated = vector_path.read_text(encoding="utf-8")
    assert original == regenerated, "network identity vector generator is not deterministic"


def test_alpha_identity_unchanged():
    import json
    data = json.loads((REPO / "test-vectors" / "network-identities.json").read_text(encoding="utf-8"))
    alpha = data["vectors"][0]
    assert alpha["network_id"] == "chainbreaker-scripture-v2"
    assert alpha["kind"] == "alpha"
    assert alpha["expected_header_hash"] == "0000a6fd1e57aafd19da552440faa94803dbf1a1773bcd9af8ce3e0ae9fd13db"
    assert alpha["expected_registry_root"] == "5814321ad489e630fef0350b1bff591d5cee8a821c00fa40a2cb2c99bd5b3186"


def test_python_derives_vector_values():
    import json
    import sys

    sys.path.insert(0, str(REPO))
    try:
        from chainbreaker.network_identity import derive_network_identity
        data = json.loads((REPO / "test-vectors" / "network-identities.json").read_text(encoding="utf-8"))
        for v in data["vectors"]:
            identity = derive_network_identity(
                network_id=v["network_id"],
                governance_keys=v["governance_keys"],
                governance_threshold=v["governance_threshold"],
                kind=v["kind"],
                genesis_timestamp=v["genesis_timestamp"],
                max_mining_iterations=10_000_000,
            )
            assert identity.genesis_registry_root == v["expected_registry_root"]
            assert identity.genesis_header_bytes.hex() == v["expected_header_bytes_hex"]
            assert identity.genesis_hash == v["expected_header_hash"]
    finally:
        sys.path.remove(str(REPO))


def test_negative_vectors_produce_different_results():
    import json
    import sys

    sys.path.insert(0, str(REPO))
    try:
        from chainbreaker.network_identity import derive_network_identity
        data = json.loads((REPO / "test-vectors" / "network-identities.json").read_text(encoding="utf-8"))
        base = data["vectors"][1]
        base_identity = derive_network_identity(
            network_id=base["network_id"],
            governance_keys=base["governance_keys"],
            governance_threshold=base["governance_threshold"],
            kind=base["kind"],
            genesis_timestamp=base["genesis_timestamp"],
            max_mining_iterations=10_000_000,
        )
        for neg in data["negative_vectors"]:
            if neg["variant"] == "wrong_genesis_root":
                identity = derive_network_identity(
                    network_id=neg["network_id"],
                    governance_keys=neg["governance_keys"],
                    governance_threshold=neg["governance_threshold"],
                    kind="test",
                    genesis_timestamp=neg["genesis_timestamp"],
                    max_mining_iterations=10_000_000,
                )
                assert identity.genesis_registry_root != neg["tampered_registry_root"]
            else:
                identity = derive_network_identity(
                    network_id=neg["network_id"],
                    governance_keys=neg["governance_keys"],
                    governance_threshold=neg["governance_threshold"],
                    kind="test",
                    genesis_timestamp=neg["genesis_timestamp"],
                    max_mining_iterations=10_000_000,
                )
                assert identity.genesis_hash != base_identity.genesis_hash
                assert identity.genesis_registry_root != base_identity.genesis_registry_root
    finally:
        sys.path.remove(str(REPO))
