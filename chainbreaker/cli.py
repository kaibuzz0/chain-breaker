
"""Command-line interface for Chain-Breaker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from .archive import Archive
from .block import create_genesis_block
from .chain import Ledger
from .cli_v2 import v2
from .witness import (
    CuratorSigner,
    Registry,
    verify_transaction_witnesses,
)


@click.group()
@click.version_option(version=__import__("chainbreaker").__version__, prog_name="chainbreaker")
def cli() -> None:
    """Chain-Breaker scripture preservation ledger."""


@cli.command()
def genesis() -> None:
    """Print the canonical genesis block."""
    g = create_genesis_block()
    click.echo(json.dumps(g.to_dict(), indent=2))


@cli.command()
@click.option("--data-dir", default="./chainbreaker-data", help="Ledger data directory")
@click.option("--blocks-file", default="chain.json", help="Chain storage file")
def status(data_dir: str, blocks_file: str) -> None:
    """Show ledger status."""
    path = Path(data_dir) / blocks_file
    if not path.exists():
        click.echo(f"No chain found at {path}; starting from genesis.")
        ledger = Ledger()
    else:
        with open(path, encoding="utf-8") as f:
            ledger = Ledger.from_dict(json.load(f))
    click.echo(f"Height: {ledger.height()}")
    click.echo(f"Tip: {ledger.last_block.hash}")
    click.echo(f"Chain work: {ledger.chain_work():.6f}")
    click.echo(f"Valid: {ledger.validate_chain()}")


@cli.command()
@click.option("--data-dir", default="./chainbreaker-data", help="Ledger data directory")
@click.option("--blocks-file", default="chain.json", help="Chain storage file")
@click.option("--registry-file", default="registry.json", help="Curator registry file")
@click.option("--manifest-hash", required=True, help="Hash of signed manifest to anchor")
@click.option("--max-iters", default=10_000_000, help="Mining iteration limit")
def mine(data_dir: str, blocks_file: str, registry_file: str, manifest_hash: str, max_iters: int) -> None:
    """Mine a new block anchoring a signed manifest."""
    data_dir_path = Path(data_dir)
    chain_path = data_dir_path / blocks_file
    registry_path = data_dir_path / registry_file

    archive = Archive(str(data_dir_path / "archive"))
    manifest = archive.get_manifest(manifest_hash)

    if chain_path.exists():
        with open(chain_path, encoding="utf-8") as f:
            ledger = Ledger.from_dict(json.load(f))
    else:
        ledger = Ledger()

    registry = Registry.from_list(json.loads(registry_path.read_text(encoding="utf-8"))) if registry_path.exists() else Registry()

    height = ledger.height() + 1
    signer = CuratorSigner("alpha")  # placeholder signer identity
    body = manifest
    w = signer.sign_manifest(body)
    tx: dict[str, Any] = {
        "version": 1,
        "type": "scripture",
        "body": body,
        "witnesses": [w],
    }

    def validator(t: dict[str, Any]) -> bool:
        return verify_transaction_witnesses(registry, t, block_height=height)

    ledger.transaction_validator = validator
    block = ledger.mine_block([tx], max_iterations=max_iters)
    if not ledger.add_block(block):
        raise click.ClickException("Failed to accept mined block")

    chain_path.parent.mkdir(parents=True, exist_ok=True)
    with open(chain_path, "w", encoding="utf-8") as f:
        json.dump(ledger.to_dict(), f, indent=2)
    click.echo(f"Mined block {ledger.height()}: {block.hash}")


@cli.group()
def curator() -> None:
    """Curator key management."""


@curator.command("generate")
@click.option("--curator-id", required=True, help="Curator identifier")
def curator_generate(curator_id: str) -> None:
    """Generate a curator keypair."""
    signer = CuratorSigner(curator_id)
    click.echo(json.dumps({
        "curator_id": curator_id,
        "public_key_hex": signer.public_key_hex,
    }, indent=2))


@cli.group()
def archive() -> None:
    """Document archive commands."""


@archive.command("add")
@click.option("--data-dir", default="./chainbreaker-data", help="Archive directory")
@click.option("--file", required=True, type=click.Path(exists=True), help="File to archive")
@click.option("--title", required=True, help="Document title")
@click.option("--media-type", default="application/octet-stream", help="Media type")
@click.option("--language", default=None, help="Language code")
@click.option("--source", default=None, help="Source description")
@click.option("--source-uri", default=None, help="Source URI")
@click.option("--license", default=None, help="License or rights status")
def archive_add(data_dir: str, file: str, title: str, media_type: str, language: str | None, source: str | None, source_uri: str | None, license: str | None) -> None:
    """Add a document to the archive and print its manifest hash."""
    archive_obj = Archive(str(Path(data_dir) / "archive"))
    with open(file, "rb") as f:
        data = f.read()
    mh = archive_obj.add_document(
        data,
        title=title,
        media_type=media_type,
        language=language,
        source=source,
        source_uri=source_uri,
        license=license,
    )
    click.echo(f"Manifest hash: {mh}")


cli.add_command(v2)


def main() -> None:
    cli()
