
"""CLI smoke tests using click's CliRunner."""

import json

from click.testing import CliRunner

from chainbreaker.cli import cli


def test_cli_genesis():
    runner = CliRunner()
    result = runner.invoke(cli, ["genesis"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["header"]["version"] == 2
    assert data["header"]["registry_root"] is not None
    from chainbreaker.block import GENESIS_HASH
    assert data["hash"] == GENESIS_HASH


def test_cli_status_no_chain():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["status", "--data-dir", "./empty"])
        assert result.exit_code == 0
        assert "Height: 0" in result.output


def test_cli_curator_generate():
    runner = CliRunner()
    result = runner.invoke(cli, ["curator", "generate", "--curator-id", "test"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["curator_id"] == "test"
    assert len(data["public_key_hex"]) == 64
