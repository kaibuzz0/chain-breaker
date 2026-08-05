"""Tests for Protocol v2 CLI commands.

Milestone A: genesis, chain init/verify, curator generate.
Milestone B: block mine/add with full validation and installed-entry-point smoke tests.
Milestone C: governance CLI (register, rotate, revoke) with end-to-end ledger flows.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from chainbreaker.block import GENESIS_HASH, GENESIS_REGISTRY_ROOT, GENESIS_TARGET_HEX, NETWORK_ID
from chainbreaker.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


def _installed_python() -> str:
    """Return the Python interpreter running the tests."""
    return sys.executable


def _run_installed(args: list[str], cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run the installed chainbreaker entry point as a subprocess."""
    repo = Path(__file__).resolve().parents[1]
    workdir = cwd or repo
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo)
    return subprocess.run(
        [_installed_python(), "-m", "chainbreaker", *args],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        check=check,
        env=env,
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Milestone A: read-only commands
# ---------------------------------------------------------------------------


def test_v2_genesis(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["v2", "genesis"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["protocol_version"] == 2
    assert data["network_id"] == NETWORK_ID
    assert data["genesis_hash"] == GENESIS_HASH
    assert data["genesis_registry_root"] == GENESIS_REGISTRY_ROOT
    assert data["governance_threshold"] == 2
    assert len(data["governance_public_keys"]) == 3
    assert data["genesis_block"]["hash"] == GENESIS_HASH


def test_v2_chain_init_and_verify(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["v2", "chain", "init", "--output", "ledger.json"])
        assert result.exit_code == 0
        init = json.loads(result.output)
        assert init["height"] == 0
        assert init["genesis_hash"] == GENESIS_HASH
        assert init["registry_root"] == GENESIS_REGISTRY_ROOT
        assert Path("ledger.json").exists()

        result = runner.invoke(cli, ["v2", "chain", "verify", "--ledger", "ledger.json"])
        assert result.exit_code == 0
        verify = json.loads(result.output)
        assert verify["valid"] is True
        assert verify["height"] == 0
        assert verify["tip_hash"] == GENESIS_HASH
        assert verify["registry_root"] == GENESIS_REGISTRY_ROOT
        assert verify["curator_count"] == 0


def test_v2_chain_init_refuses_overwrite(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        Path("ledger.json").write_text("existing", encoding="utf-8")
        result = runner.invoke(cli, ["v2", "chain", "init", "--output", "ledger.json"])
        assert result.exit_code != 0
        assert "refusing to overwrite" in result.output


def test_v2_chain_init_force_overwrite(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        Path("ledger.json").write_text("existing", encoding="utf-8")
        result = runner.invoke(cli, ["v2", "chain", "init", "--output", "ledger.json", "--force"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["height"] == 0


def test_v2_chain_verify_missing_ledger(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["v2", "chain", "verify", "--ledger", "missing.json"])
        assert result.exit_code != 0


def test_v2_chain_verify_bad_network_id(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        ledger = {"network_id": "wrong", "chain": [], "chain_work": 0}
        Path("ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        result = runner.invoke(cli, ["v2", "chain", "verify", "--ledger", "ledger.json"])
        assert result.exit_code != 0


def test_v2_curator_generate(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "sk.hex", "--public-key", "pk.hex"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["public_key_hex"]
        assert len(data["public_key_hex"]) == 64
        assert Path("sk.hex").exists()
        assert Path("pk.hex").exists()
        # Private key should not appear in output.
        assert data["public_key_hex"] not in Path("sk.hex").read_text(encoding="utf-8")


def test_v2_curator_generate_refuses_overwrite(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        Path("sk.hex").write_text("x", encoding="utf-8")
        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "sk.hex"])
        assert result.exit_code != 0


def test_v2_ledger_governance_keys_round_trip_and_validate(runner: CliRunner) -> None:
    """A ledger with a custom governance keyset must survive serialization and still validate governance tx after reload."""
    from chainbreaker.chain import Ledger
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        led = Ledger(governance_keys=gov_key_hexes, governance_threshold=2)
        assert list(led.governance_keys) == gov_key_hexes
        assert led.governance_threshold == 2

        Path("ledger.json").write_text(json.dumps(led.to_dict()), encoding="utf-8")
        reloaded = Ledger.from_dict(_load_json(Path("ledger.json")))
        assert list(reloaded.governance_keys) == gov_key_hexes
        assert reloaded.governance_threshold == 2

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "curator_sk.hex", "--public-key", "curator_pk.hex", "--curator-id", "alpha"])
        curator_pk = json.loads(result.output)["public_key_hex"]

        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--activation-height", "5",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code == 0

        _mine_add_block(runner, "ledger.json", "block_1.json", transactions="reg_tx.json")
        result = runner.invoke(cli, ["v2", "chain", "verify", "--ledger", "ledger.json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["valid"] is True



def test_v2_curator_generate_does_not_print_private_key(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "sk.hex"])
        assert result.exit_code == 0
        sk_hex = Path("sk.hex").read_text(encoding="utf-8").strip()
        assert sk_hex not in result.output


# ---------------------------------------------------------------------------
# Milestone B: block mine/add end-to-end
# ---------------------------------------------------------------------------


def _init_ledger(runner: CliRunner, name: str = "ledger.json") -> dict[str, Any]:
    result = runner.invoke(cli, ["v2", "chain", "init", "--output", name])
    assert result.exit_code == 0
    return json.loads(result.output)


def _mine_block(runner: CliRunner, ledger: str, block: str, max_iters: int = 10_000_000) -> dict[str, Any]:
    result = runner.invoke(cli, [
        "v2", "block", "mine",
        "--ledger", ledger,
        "--output", block,
        "--max-iters", str(max_iters),
    ])
    assert result.exit_code == 0
    return json.loads(result.output)


def _verify_ledger(runner: CliRunner, ledger: str) -> dict[str, Any]:
    result = runner.invoke(cli, ["v2", "chain", "verify", "--ledger", ledger])
    assert result.exit_code == 0
    return json.loads(result.output)


def test_v2_block_mine_creates_block_file(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        result = _mine_block(runner, "ledger.json", "block.json")
        assert Path("block.json").exists()
        assert result["height"] == 1
        assert result["target"] == GENESIS_TARGET_HEX
        assert len(result["target"]) == 64
        block = _load_json(Path("block.json"))
        assert block["header"]["version"] == 2
        assert block["header"]["prev_hash"] == GENESIS_HASH


def test_v2_block_mine_does_not_alter_ledger(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        before = _verify_ledger(runner, "ledger.json")
        _mine_block(runner, "ledger.json", "block.json")
        after = _verify_ledger(runner, "ledger.json")
        assert after["height"] == before["height"]
        assert after["tip_hash"] == before["tip_hash"]
        assert after["chain_work"] == before["chain_work"]


def test_v2_block_mine_output_is_deterministic_except_nonce_and_hash(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        # Mine with explicit distinct timestamps to guarantee distinct blocks.
        a = _mine_block(runner, "ledger.json", "block_a.json")
        b = runner.invoke(cli, [
            "v2", "block", "mine",
            "--ledger", "ledger.json",
            "--output", "block_b.json",
            "--max-iters", "10000000",
            "--timestamp", "1800000000",
        ])
        assert b.exit_code == 0
        b_data = json.loads(b.output)
        assert a["target"] == b_data["target"]
        assert a["registry_root"] == b_data["registry_root"]
        assert a["height"] == b_data["height"]
        assert a["hash"] != b_data["hash"]


def test_v2_block_mine_refuses_overwrite(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        Path("block.json").write_text("existing", encoding="utf-8")
        result = runner.invoke(cli, ["v2", "block", "mine", "--ledger", "ledger.json", "--output", "block.json"])
        assert result.exit_code != 0
        assert "refusing to overwrite" in result.output


def test_v2_block_add_valid_block(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        before = _verify_ledger(runner, "ledger.json")
        block = _mine_block(runner, "ledger.json", "block.json")
        result = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block.json"])
        assert result.exit_code == 0
        add = json.loads(result.output)
        assert add["height"] == before["height"] + 1
        assert add["tip_hash"] == block["hash"]
        assert int(add["chain_work"]) > int(before["chain_work"])

        after = _verify_ledger(runner, "ledger.json")
        assert after["valid"] is True
        assert after["height"] == add["height"]
        assert after["tip_hash"] == add["tip_hash"]


def test_v2_block_add_same_block_twice_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        _mine_block(runner, "ledger.json", "block.json")
        first = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block.json"])
        assert first.exit_code == 0
        second = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block.json"])
        assert second.exit_code != 0


def test_v2_block_add_from_wrong_ledger_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner, "ledger_a.json")
        _init_ledger(runner, "ledger_b.json")
        # Mine and add a first block on ledger A, so A and B tips diverge.
        _mine_block(runner, "ledger_a.json", "block_1.json")
        r = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger_a.json", "--block", "block_1.json"])
        assert r.exit_code == 0
        # Mine a second block on ledger A; its prev_hash cannot match ledger B tip.
        _mine_block(runner, "ledger_a.json", "block_a.json")
        result = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger_b.json", "--block", "block_a.json"])
        assert result.exit_code != 0
        assert "previous hash" in result.output.lower()


def test_v2_block_add_malformed_block_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        Path("block.json").write_text("not valid json", encoding="utf-8")
        result = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block.json"])
        assert result.exit_code != 0


def test_v2_block_add_trailing_bytes_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        _mine_block(runner, "ledger.json", "block.json")
        raw = Path("block.json").read_text(encoding="utf-8")
        Path("block_trailing.json").write_text(raw + "\nextra", encoding="utf-8")
        result = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block_trailing.json"])
        assert result.exit_code != 0
        assert "trailing" in result.output


def test_v2_block_add_invalid_pow_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        _mine_block(runner, "ledger.json", "block.json")
        block = _load_json(Path("block.json"))
        block["header"]["nonce"] = 0
        # Recompute hash field so structural checks pass before PoW check.
        block["hash"] = "0" * 64
        Path("block_bad_pow.json").write_text(json.dumps(block), encoding="utf-8")
        result = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block_bad_pow.json"])
        assert result.exit_code != 0


def test_v2_block_add_wrong_registry_root_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        _mine_block(runner, "ledger.json", "block.json")
        block = _load_json(Path("block.json"))
        block["header"]["registry_root"] = "0" * 64
        Path("block_bad_root.json").write_text(json.dumps(block), encoding="utf-8")
        result = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block_bad_root.json"])
        assert result.exit_code != 0
        assert "registry root" in result.output.lower()


def test_v2_chain_verify_corrupted_ledger_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        _mine_block(runner, "ledger.json", "block.json")
        result = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block.json"])
        assert result.exit_code == 0

        ledger = _load_json(Path("ledger.json"))
        # Corrupt the tip header nonce so the stored proof of work becomes invalid.
        ledger["chain"][-1]["header"]["nonce"] = 0
        # Remove the cached hash so from_dict recomputes from the corrupted header.
        ledger["chain"][-1].pop("hash", None)
        Path("ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

        result = runner.invoke(cli, ["v2", "chain", "verify", "--ledger", "ledger.json"])
        assert result.exit_code != 0


def test_v2_chain_verify_wrong_network_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner)
        ledger = _load_json(Path("ledger.json"))
        ledger["network_id"] = "wrong-network"
        Path("ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        result = runner.invoke(cli, ["v2", "chain", "verify", "--ledger", "ledger.json"])
        assert result.exit_code != 0
        assert "network" in result.output.lower()


def test_v2_chain_init_atomic_write_failure_preserves_original(runner: CliRunner, monkeypatch) -> None:
    from chainbreaker import cli_v2

    with runner.isolated_filesystem():
        Path("ledger.json").write_text("original", encoding="utf-8")
        monkeypatch.setattr(cli_v2, "_atomic_write", lambda path, data, mode=0o644: (_ for _ in ()).throw(RuntimeError("disk full")))
        result = runner.invoke(cli, ["v2", "chain", "init", "--output", "ledger.json", "--force"])
        assert result.exit_code != 0
        assert Path("ledger.json").read_text(encoding="utf-8") == "original"


def test_v2_installed_cli_end_to_end_smoke(tmp_path: Path) -> None:
    """Exercise the installed console entry point for the full init-mine-add-verify flow."""
    ledger = tmp_path / "ledger.json"
    block = tmp_path / "block.json"

    init = _run_installed(["v2", "chain", "init", "--output", str(ledger)], cwd=tmp_path, check=True)
    init_data = json.loads(init.stdout)
    assert init_data["height"] == 0
    assert init_data["genesis_hash"] == GENESIS_HASH

    verify0 = _run_installed(["v2", "chain", "verify", "--ledger", str(ledger)], cwd=tmp_path, check=True)
    verify0_data = json.loads(verify0.stdout)
    assert verify0_data["valid"] is True
    assert verify0_data["height"] == 0

    mine = _run_installed([
        "v2", "block", "mine",
        "--ledger", str(ledger),
        "--output", str(block),
        "--max-iters", "10000000",
    ], cwd=tmp_path, check=True)
    mine_data = json.loads(mine.stdout)
    assert mine_data["height"] == 1
    assert mine_data["target"] == GENESIS_TARGET_HEX
    assert len(mine_data["target"]) == 64

    verify1 = _run_installed(["v2", "chain", "verify", "--ledger", str(ledger)], cwd=tmp_path, check=True)
    verify1_data = json.loads(verify1.stdout)
    assert verify1_data["height"] == 0, "ledger must not change during mining"

    add = _run_installed(["v2", "block", "add", "--ledger", str(ledger), "--block", str(block)], cwd=tmp_path, check=True)
    add_data = json.loads(add.stdout)
    assert add_data["height"] == 1
    assert add_data["tip_hash"] == mine_data["hash"]

    verify2 = _run_installed(["v2", "chain", "verify", "--ledger", str(ledger)], cwd=tmp_path, check=True)
    verify2_data = json.loads(verify2.stdout)
    assert verify2_data["valid"] is True
    assert verify2_data["height"] == 1
    assert verify2_data["tip_hash"] == mine_data["hash"]
    assert int(verify2_data["chain_work"]) > int(verify0_data["chain_work"])


def test_v2_block_add_refuses_overwrite_output(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        _init_ledger(runner, "ledger_a.json")
        _init_ledger(runner, "ledger_b.json")
        # Add first block to ledger_a, keeping ledger_b at genesis.
        _mine_block(runner, "ledger_a.json", "block_1.json")
        r = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger_a.json", "--block", "block_1.json"])
        assert r.exit_code == 0
        # Mine a second block against ledger_a.
        _mine_block(runner, "ledger_a.json", "block_2.json")
        # Copy ledger_a to ledger_b and create an existing output file.
        Path("ledger_b.json").write_text(Path("ledger_a.json").read_text(encoding="utf-8"), encoding="utf-8")
        Path("out.json").write_text("existing", encoding="utf-8")
        # Add block_2 with --output out.json; should refuse to overwrite before validation.
        result = runner.invoke(cli, [
            "v2", "block", "add",
            "--ledger", "ledger_b.json",
            "--block", "block_2.json",
            "--output", "out.json",
        ])
        assert result.exit_code != 0
        assert "refusing to overwrite" in result.output
        # Ensure ledger_b was not modified.
        ledger_b_after = json.loads(Path("ledger_b.json").read_text(encoding="utf-8"))
        assert ledger_b_after["chain"][-1]["hash"] != GENESIS_HASH
        assert Path("out.json").read_text(encoding="utf-8") == "existing"


def _generate_governance_keys(num=3):
    from chainbreaker.crypto import encode_public_key, generate_keypair
    keys = []
    for _ in range(num):
        sk, pk = generate_keypair()
        keys.append((sk.private_bytes_raw().hex(), encode_public_key(pk)))
    return keys

def _write_key_hex(path: Path, hex_key: str) -> None:
    path.write_text(hex_key + "\n", encoding="utf-8")

def _create_ledger_with_governance(path: Path, governance_keys: list[str], threshold: int = 2):
    from chainbreaker.chain import Ledger
    led = Ledger(governance_keys=governance_keys, governance_threshold=threshold)
    path.write_text(json.dumps(led.to_dict()), encoding="utf-8")
    return led

def _mine_add_block(runner: CliRunner, ledger: str, block: str, transactions: str | None = None):
    args = ["v2", "block", "mine", "--ledger", ledger, "--output", block, "--max-iters", "10000000"]
    if transactions is not None:
        args.extend(["--transactions", transactions])
    result = runner.invoke(cli, args)
    assert result.exit_code == 0
    result = runner.invoke(cli, ["v2", "block", "add", "--ledger", ledger, "--block", block])
    assert result.exit_code == 0
    return json.loads(result.output)

# ---------------------------------------------------------------------------
# Milestone C: governance end-to-end
# ---------------------------------------------------------------------------

def test_v2_governance_register_valid_2of3(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", "5c058810d893853fb47c87af463b8c807b39dcbdfbfcec4d407d844122a13824",
            "--activation-height", "5",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["action"] == "curator_register"
        assert data["curator_id"] == "alpha"
        assert data["previous_registry_root"]
        assert data["canonical_txid"]

        tx = _load_json(Path("reg_tx.json"))
        assert tx["type"] == "governance"
        body = tx["body"]
        assert body["action"] == "curator_register"
        assert body["curator_id"] == "alpha"
        assert body["activation_height"] == 5
        assert len(body["governance_signatures"]) == 2
        indices = [s["key_index"] for s in body["governance_signatures"]]
        assert indices == sorted(indices)
        assert Path("gov_0.hex").read_text(encoding="utf-8").strip() not in result.output
        assert Path("gov_1.hex").read_text(encoding="utf-8").strip() not in result.output

def test_v2_governance_register_then_mine_and_add(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "curator_sk.hex", "--public-key", "curator_pk.hex", "--curator-id", "alpha"])
        assert result.exit_code == 0
        curator_pk = json.loads(result.output)["public_key_hex"]

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--activation-height", "5",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code == 0

        result = runner.invoke(cli, [
            "v2", "block", "mine",
            "--ledger", "ledger.json",
            "--transactions", "reg_tx.json",
            "--output", "block_1.json",
            "--max-iters", "10000000",
        ])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block_1.json"])
        assert result.exit_code == 0
        add = json.loads(result.output)
        assert add["height"] == 1
        assert add["curator_count"] == 1

def test_v2_curator_inactive_before_activation_height_and_active_at_height(runner: CliRunner) -> None:
    from chainbreaker.chain import Ledger
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "curator_sk.hex", "--public-key", "curator_pk.hex", "--curator-id", "alpha"])
        curator_pk = json.loads(result.output)["public_key_hex"]

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--activation-height", "3",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code == 0

        _mine_add_block(runner, "ledger.json", "block_1.json", transactions="reg_tx.json")
        _mine_add_block(runner, "ledger.json", "block_2.json")
        _mine_add_block(runner, "ledger.json", "block_3.json")

        led = Ledger.from_dict(_load_json(Path("ledger.json")))
        record = led.registry_state_at(2).by_id("alpha")
        assert record is not None
        assert not record.is_active_at(2)
        record = led.registry_state_at(3).by_id("alpha")
        assert record is not None
        assert record.is_active_at(3)

def test_v2_governance_rotate_key(runner: CliRunner) -> None:
    from chainbreaker.chain import Ledger
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "alpha_sk.hex", "--public-key", "alpha_pk.hex", "--curator-id", "alpha"])
        alpha_pk = json.loads(result.output)["public_key_hex"]

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "beta_sk.hex", "--public-key", "beta_pk.hex", "--curator-id", "beta"])
        beta_pk = json.loads(result.output)["public_key_hex"]

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)

        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", alpha_pk,
            "--activation-height", "2",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_alpha.json",
        ])
        assert result.exit_code == 0
        _mine_add_block(runner, "ledger.json", "block_1.json", transactions="reg_alpha.json")
        _mine_add_block(runner, "ledger.json", "block_2.json")

        result = runner.invoke(cli, [
            "v2", "governance", "rotate",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", alpha_pk,
            "--new-public-key", beta_pk,
            "--activation-height", "4",
            "--curator-private-key", "alpha_sk.hex",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "rotate_alpha.json",
        ])
        assert result.exit_code == 0
        _mine_add_block(runner, "ledger.json", "block_3.json", transactions="rotate_alpha.json")
        _mine_add_block(runner, "ledger.json", "block_4.json")

        led = Ledger.from_dict(_load_json(Path("ledger.json")))
        assert led.registry_state_at(2).key_was_valid_at("alpha", alpha_pk, 2)
        assert led.registry_state_at(4).key_was_valid_at("alpha", beta_pk, 4)

def test_v2_governance_revoke_key(runner: CliRunner) -> None:
    from chainbreaker.chain import Ledger
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "alpha_sk.hex", "--public-key", "alpha_pk.hex", "--curator-id", "alpha"])
        alpha_pk = json.loads(result.output)["public_key_hex"]

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", alpha_pk,
            "--activation-height", "2",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_alpha.json",
        ])
        assert result.exit_code == 0
        _mine_add_block(runner, "ledger.json", "block_1.json", transactions="reg_alpha.json")
        _mine_add_block(runner, "ledger.json", "block_2.json")

        result = runner.invoke(cli, [
            "v2", "governance", "revoke",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", alpha_pk,
            "--revocation-height", "4",
            "--reason", "compromise",
            "--curator-private-key", "alpha_sk.hex",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "revoke_alpha.json",
        ])
        assert result.exit_code == 0
        _mine_add_block(runner, "ledger.json", "block_3.json", transactions="revoke_alpha.json")
        _mine_add_block(runner, "ledger.json", "block_4.json")

        led = Ledger.from_dict(_load_json(Path("ledger.json")))
        assert led.registry_state_at(2).key_was_valid_at("alpha", alpha_pk, 2)
        assert not led.registry_state_at(4).key_was_valid_at("alpha", alpha_pk, 4)

def test_v2_governance_insufficient_signatures_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "curator_sk.hex", "--public-key", "curator_pk.hex", "--curator-id", "alpha"])
        curator_pk = json.loads(result.output)["public_key_hex"]

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--activation-height", "5",
            "--governance-key", "gov_0.hex",
            "--key-index", "0",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code != 0
        assert "insufficient" in result.output.lower() or "governance authorization failed" in result.output.lower()

def test_v2_governance_duplicate_signatures_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "curator_sk.hex", "--public-key", "curator_pk.hex", "--curator-id", "alpha"])
        curator_pk = json.loads(result.output)["public_key_hex"]

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--activation-height", "5",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_0.hex",
            "--key-index", "0",
            "--key-index", "0",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code != 0
        assert "duplicate" in result.output.lower()

def test_v2_governance_unknown_signer_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "wrong_sk.hex", "--public-key", "wrong_pk.hex", "--curator-id", "alpha"])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "curator_sk.hex", "--public-key", "curator_pk.hex", "--curator-id", "alpha"])
        curator_pk = json.loads(result.output)["public_key_hex"]

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--activation-height", "5",
            "--governance-key", "wrong_sk.hex",
            "--key-index", "0",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code != 0
        assert "out of range" in result.output.lower() or "governance authorization failed" in result.output.lower()

def test_v2_governance_mutated_transaction_after_signing_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "curator_sk.hex", "--public-key", "curator_pk.hex", "--curator-id", "alpha"])
        curator_pk = json.loads(result.output)["public_key_hex"]

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--activation-height", "5",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code == 0

        tx = _load_json(Path("reg_tx.json"))
        tx["body"]["curator_id"] = "beta"
        Path("reg_tx.json").write_text(json.dumps(tx), encoding="utf-8")

        result = runner.invoke(cli, [
            "v2", "block", "mine",
            "--ledger", "ledger.json",
            "--transactions", "reg_tx.json",
            "--output", "block.json",
            "--max-iters", "10000000",
        ])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block.json"])
        assert result.exit_code != 0

def test_v2_governance_stale_registry_root_rejected(runner: CliRunner) -> None:
    from chainbreaker.registry_state import registry_root
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "curator_sk.hex", "--public-key", "curator_pk.hex", "--curator-id", "alpha"])
        curator_pk = json.loads(result.output)["public_key_hex"]

        led = _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        stale_root = registry_root(led.registry_state_at(0))

        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--activation-height", "5",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code == 0
        _mine_add_block(runner, "ledger.json", "block_1.json")

        # Build another registration but replace previous root with stale pre-block root.
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "beta",
            "--public-key", curator_pk,
            "--activation-height", "10",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx_2.json",
        ])
        assert result.exit_code == 0
        tx = _load_json(Path("reg_tx_2.json"))
        tx["body"]["previous_registry_root"] = stale_root
        Path("reg_tx_2.json").write_text(json.dumps(tx), encoding="utf-8")

        result = runner.invoke(cli, [
            "v2", "block", "mine",
            "--ledger", "ledger.json",
            "--transactions", "reg_tx_2.json",
            "--output", "block_2.json",
            "--max-iters", "10000000",
            "--timestamp", "1800000002",
        ])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block_2.json"])
        assert result.exit_code != 0
        assert "rejected" in result.output.lower() or "failed" in result.output.lower()

def test_v2_governance_replayed_transaction_rejected(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "curator_sk.hex", "--public-key", "curator_pk.hex", "--curator-id", "alpha"])
        curator_pk = json.loads(result.output)["public_key_hex"]

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--activation-height", "5",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code == 0
        _mine_add_block(runner, "ledger.json", "block_1.json")

        result = runner.invoke(cli, [
            "v2", "block", "mine",
            "--ledger", "ledger.json",
            "--transactions", "reg_tx.json",
            "--output", "block_2.json",
            "--max-iters", "10000000",
            "--timestamp", "1800000002",
        ])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["v2", "block", "add", "--ledger", "ledger.json", "--block", "block_2.json"])
        assert result.exit_code != 0
        assert "rejected" in result.output.lower() or "failed" in result.output.lower()

def test_v2_governance_private_key_never_printed(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "curator_sk.hex", "--public-key", "curator_pk.hex", "--curator-id", "alpha"])
        curator_pk = json.loads(result.output)["public_key_hex"]
        curator_sk = Path("curator_sk.hex").read_text(encoding="utf-8").strip()

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--activation-height", "5",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code == 0
        assert curator_sk not in result.output
        assert Path("gov_0.hex").read_text(encoding="utf-8").strip() not in result.output
        assert Path("gov_1.hex").read_text(encoding="utf-8").strip() not in result.output
        tx = _load_json(Path("reg_tx.json"))
        assert curator_sk not in json.dumps(tx)

        _mine_add_block(runner, "ledger.json", "block_1.json", transactions="reg_tx.json")
        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "next_sk.hex", "--public-key", "next_pk.hex", "--curator-id", "alpha"])
        next_pk = json.loads(result.output)["public_key_hex"]
        next_sk = Path("next_sk.hex").read_text(encoding="utf-8").strip()

        result = runner.invoke(cli, [
            "v2", "governance", "rotate",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--new-public-key", next_pk,
            "--activation-height", "10",
            "--curator-private-key", "curator_sk.hex",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "rotate_tx.json",
        ])
        assert result.exit_code == 0
        assert curator_sk not in result.output
        assert next_sk not in result.output
        assert Path("gov_0.hex").read_text(encoding="utf-8").strip() not in result.output
        assert Path("gov_1.hex").read_text(encoding="utf-8").strip() not in result.output

        _mine_add_block(runner, "ledger.json", "block_2.json", transactions="rotate_tx.json")
        result = runner.invoke(cli, [
            "v2", "governance", "revoke",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", next_pk,
            "--revocation-height", "15",
            "--reason", "compromise",
            "--curator-private-key", "next_sk.hex",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "revoke_tx.json",
        ])
        assert result.exit_code == 0
        assert next_sk not in result.output
        assert Path("gov_0.hex").read_text(encoding="utf-8").strip() not in result.output
        assert Path("gov_1.hex").read_text(encoding="utf-8").strip() not in result.output

def test_v2_governance_transaction_overwrite_refusal_and_force(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        governance_keys = _generate_governance_keys(3)
        gov_key_hexes = [pk for _, pk in governance_keys]
        for i, (sk_hex, _) in enumerate(governance_keys):
            _write_key_hex(Path(f"gov_{i}.hex"), sk_hex)

        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "curator_sk.hex", "--public-key", "curator_pk.hex", "--curator-id", "alpha"])
        curator_pk = json.loads(result.output)["public_key_hex"]

        _create_ledger_with_governance(Path("ledger.json"), gov_key_hexes, threshold=2)
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "alpha",
            "--public-key", curator_pk,
            "--activation-height", "5",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code == 0

        Path("reg_tx.json").write_text("existing", encoding="utf-8")
        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "beta",
            "--public-key", curator_pk,
            "--activation-height", "10",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx.json",
        ])
        assert result.exit_code != 0
        assert "refusing to overwrite" in result.output.lower()

        result = runner.invoke(cli, [
            "v2", "governance", "register",
            "--ledger", "ledger.json",
            "--curator-id", "beta",
            "--public-key", curator_pk,
            "--activation-height", "10",
            "--governance-key", "gov_0.hex",
            "--governance-key", "gov_1.hex",
            "--key-index", "0",
            "--key-index", "1",
            "--output", "reg_tx.json",
            "--force",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["action"] == "curator_register"
        assert data["curator_id"] == "beta"

def test_v2_installed_governance_end_to_end_smoke(tmp_path: Path) -> None:
    from chainbreaker.chain import Ledger
    governance_keys = _generate_governance_keys(3)
    gov_key_hexes = [pk for _, pk in governance_keys]
    for i, (sk_hex, _) in enumerate(governance_keys):
        _write_key_hex(tmp_path / f"gov_{i}.hex", sk_hex)

    ledger = tmp_path / "ledger.json"
    led = Ledger(governance_keys=gov_key_hexes, governance_threshold=2)
    ledger.write_text(json.dumps(led.to_dict()), encoding="utf-8")

    result = _run_installed(["v2", "curator", "generate", "--private-key", str(tmp_path / "curator_sk.hex"), "--public-key", str(tmp_path / "curator_pk.hex"), "--curator-id", "alpha"], cwd=tmp_path, check=True)
    curator_pk = json.loads(result.stdout)["public_key_hex"]

    result = _run_installed([
        "v2", "governance", "register",
        "--ledger", str(ledger),
        "--curator-id", "alpha",
        "--public-key", curator_pk,
        "--activation-height", "5",
        "--governance-key", str(tmp_path / "gov_0.hex"),
        "--governance-key", str(tmp_path / "gov_1.hex"),
        "--key-index", "0",
        "--key-index", "1",
        "--output", str(tmp_path / "reg_tx.json"),
    ], cwd=tmp_path, check=True)
    data = json.loads(result.stdout)
    assert data["action"] == "curator_register"
    assert data["curator_id"] == "alpha"
    assert data["previous_registry_root"]

    result = _run_installed([
        "v2", "block", "mine",
        "--ledger", str(ledger),
        "--transactions", str(tmp_path / "reg_tx.json"),
        "--output", str(tmp_path / "block.json"),
        "--max-iters", "10000000",
    ], cwd=tmp_path, check=True)

    result = _run_installed([
        "v2", "block", "add",
        "--ledger", str(ledger),
        "--block", str(tmp_path / "block.json"),
    ], cwd=tmp_path, check=True)
    data = json.loads(result.stdout)
    assert data["height"] == 1
    assert data["curator_count"] == 1

    result = _run_installed(["v2", "chain", "verify", "--ledger", str(ledger)], cwd=tmp_path, check=True)
    verify = json.loads(result.stdout)
    assert verify["valid"] is True
    assert verify["height"] == 1
    assert verify["curator_count"] == 1
