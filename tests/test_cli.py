
"""CLI smoke tests using click's CliRunner."""

import json

from click.testing import CliRunner

from chainbreaker.cli import cli


def test_cli_genesis():
    runner = CliRunner()
    result = runner.invoke(cli, ["genesis"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["header"]["version"] == 1
    assert data["hash"] == "00001ec5b63d845f0afa2e499817c34a7e0de2b1c53675171645f60f36ea927c"


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
