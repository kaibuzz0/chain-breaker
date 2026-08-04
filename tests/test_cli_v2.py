"""Tests for Protocol v2 CLI commands."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from chainbreaker.cli import cli
from chainbreaker.block import (
    GENESIS_HASH,
    GENESIS_REGISTRY_ROOT,
    GENESIS_THRESHOLD,
    NETWORK_ID,
)


@pytest.fixture
def runner():
    return CliRunner()


def test_v2_genesis(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["v2", "genesis"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["protocol_version"] == 2
    assert data["network_id"] == NETWORK_ID
    assert data["genesis_hash"] == GENESIS_HASH
    assert data["genesis_registry_root"] == GENESIS_REGISTRY_ROOT
    assert data["governance_threshold"] == GENESIS_THRESHOLD
    assert len(data["governance_public_keys"]) == GENESIS_THRESHOLD + 1
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
        assert "refusing to overwrite" in result.output or "refusing to overwrite" in str(result.exception)


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


def test_v2_curator_generate_does_not_print_private_key(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["v2", "curator", "generate", "--private-key", "sk.hex"])
        assert result.exit_code == 0
        sk_hex = Path("sk.hex").read_text(encoding="utf-8").strip()
        assert sk_hex not in result.output
