
"""Command-line interface for Chain-Breaker."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import click

from . import archive, chain, witness
from .archive import ContentArchive, DocumentManifest
from .block import create_genesis_block
from .chain import Ledger
from .crypto import generate_keypair, encode_private_key, encode_public_key, decode_private_key
from .witness import Registry, Curator, sign_transaction, verify_transaction_witnesses


DEFAULT_NETWORK = "chainbreaker-scripture-v1"


@click.group()
@click.option("--network", default=DEFAULT_NETWORK, help="Network identifier.")
@click.pass_context
def cli(ctx: click.Context, network: str) -> None:
    ctx.ensure_object(dict)
    ctx.obj["network"] = network


@cli.command()
def genesis() -> None:
    """Print the canonical genesis block."""
    g = create_genesis_block()
    click.echo(json.dumps(g.to_dict(), indent=2))


@cli.command()
@click.option("--data-dir", default="chainbreaker-data", help="Storage directory.")
@click.pass_context
def status(ctx: click.Context, data_dir: str) -> None:
    """Show ledger status."""
    ledger_path = Path(data_dir) / "ledger.json"
    if ledger_path.exists():
        with open(ledger_path, "r", encoding="utf-8") as f:
            ledger = Ledger.from_dict(json.load(f))
    else:
        ledger = Ledger()
    click.echo(f"Height: {ledger.height}")
    click.echo(f"Tip:   {ledger.last_block.hash}")
    click.echo(f"Valid: {ledger.validate_chain()}")


@cli.group()
def archive_cmd() -> None:
    """Content-addressed archive commands."""


@archive_cmd.command("add")
@click.argument("path", type=click.Path(exists=True))
@click.option("--title", required=True, help="Document title.")
@click.option("--language", default=None, help="Language code.")
@click.option("--source", default=None, help="Source / provenance.")
@click.option("--data-dir", default="chainbreaker-data", help="Storage directory.")
def archive_add(path: str, title: str, language: Optional[str],
                source: Optional[str], data_dir: str) -> None:
    """Add a document to the content archive."""
    data_dir_path = Path(data_dir)
    data_dir_path.mkdir(parents=True, exist_ok=True)
    content = Path(path).read_bytes()
    archive = ContentArchive(data_dir_path)
    manifest = DocumentManifest(
        schema="chainbreaker-manifest-v1",
        content_hash="",  # filled after store
        size=len(content),
        media_type="application/octet-stream",
        title=title,
        language=language,
        source=source,
        provenance={"added_at": int(time.time()), "source_file": os.path.basename(path)},
        timestamp=int(time.time()),
    )
    stored = archive.store(content, manifest)
    click.echo(json.dumps(stored.to_dict(), indent=2))


@archive_cmd.command("get")
@click.argument("content_hash")
@click.option("--data-dir", default="chainbreaker-data", help="Storage directory.")
def archive_get(content_hash: str, data_dir: str) -> None:
    """Retrieve a document by content hash."""
    data = ContentArchive(Path(data_dir)).retrieve(content_hash)
    if data is None:
        raise click.ClickException("document not found")
    click.echo(data.decode("utf-8", errors="replace"))


@cli.group()
def curator() -> None:
    """Curator / witness commands."""


@curator.command("generate")
@click.option("--out", required=True, help="Path to write wallet JSON.")
def curator_generate(out: str) -> None:
    """Generate a curator Ed25519 keypair."""
    sk, pk = generate_keypair()
    wallet = {
        "private_key": encode_private_key(sk),
        "public_key": encode_public_key(pk),
    }
    Path(out).write_text(json.dumps(wallet, indent=2), encoding="utf-8")
    click.echo(f"Wrote curator key to {out}")


@curator.command("attest")
@click.option("--wallet", required=True, type=click.Path(exists=True), help="Curator wallet JSON.")
@click.option("--curator-id", required=True, help="Curator identifier.")
@click.option("--transaction", required=True, help="Transaction JSON file.")
@click.option("--out", default="-", help="Output file or - for stdout.")
@click.pass_context
def curator_attest(ctx: click.Context, wallet: str, curator_id: str,
                   transaction: str, out: str) -> None:
    """Sign a scripture transaction as a curator."""
    network = ctx.obj["network"]
    wallet_data = json.loads(Path(wallet).read_text(encoding="utf-8"))
    sk = decode_private_key(wallet_data["private_key"])
    tx = json.loads(Path(transaction).read_text(encoding="utf-8"))
    witness_obj = sign_transaction(sk, curator_id, tx, network)
    tx["witnesses"] = tx.get("witnesses", []) + [witness_obj.to_dict()]
    output = json.dumps(tx, indent=2)
    if out == "-":
        click.echo(output)
    else:
        Path(out).write_text(output, encoding="utf-8")


@cli.group()
def node() -> None:
    """Node / ledger commands."""


@node.command("mine")
@click.argument("transaction_files", nargs=-1, type=click.Path(exists=True))
@click.option("--data-dir", default="chainbreaker-data", help="Storage directory.")
@click.option("--difficulty", type=int, default=None, help="Override difficulty.")
@click.pass_context
def node_mine(ctx: click.Context, transaction_files, data_dir: str, difficulty: Optional[int]) -> None:
    """Mine pending transactions into the ledger."""
    data_dir_path = Path(data_dir)
    data_dir_path.mkdir(parents=True, exist_ok=True)
    ledger_path = data_dir_path / "ledger.json"
    if ledger_path.exists():
        ledger = Ledger.from_dict(json.load(open(ledger_path, "r", encoding="utf-8")))
    else:
        ledger = Ledger()

    transactions = []
    for path in transaction_files:
        transactions.append(json.loads(Path(path).read_text(encoding="utf-8")))

    if difficulty is not None:
        ledger.last_block.header.difficulty = difficulty

    block = ledger.mine_block(transactions)
    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump(ledger.to_dict(), f, indent=2)
    click.echo(f"Mined block {ledger.height}: {block.hash}")


@node.command("verify")
@click.option("--data-dir", default="chainbreaker-data", help="Storage directory.")
def node_verify(data_dir: str) -> None:
    """Verify the local ledger."""
    ledger_path = Path(data_dir) / "ledger.json"
    ledger = Ledger.from_dict(json.load(open(ledger_path, "r", encoding="utf-8")))
    click.echo(f"Valid chain: {ledger.validate_chain()}")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
