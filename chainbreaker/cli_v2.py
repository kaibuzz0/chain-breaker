"""Protocol v2 CLI commands for Chain-Breaker.

This module exposes the existing Protocol v2 consensus implementation through
safe, usable CLI commands. It does not modify consensus rules.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import click

from .archive import Archive
from .block import (
    GENESIS_GOVERNANCE_KEYS,
    GENESIS_HASH,
    GENESIS_NONCE,
    GENESIS_REGISTRY_ROOT,
    GENESIS_TARGET_HEX,
    GENESIS_THRESHOLD,
    NETWORK_ID,
    PROTOCOL_VERSION,
    BlockV2,
    create_genesis_block,
)
from .chain import Ledger, LedgerError
from .crypto import (
    decode_private_key,
    encode_public_key,
    generate_keypair,
    make_curator_signature,
    target_to_hex,
)
from .governance import (
    make_governance_signature,
)
from .registry_state import registry_root
from .witness import sign_attestation_v2, verify_attestation_v2

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


class CLIError(click.ClickException):
    """Controlled CLI error that does not leak a traceback by default."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_path(path_str: str) -> Path:
    """Resolve a user-supplied path, rejecting traversal outside CWD if relative.

    Absolute paths are accepted as-is; relative paths are resolved against the
    current working directory. Path traversal components are normalized by
    pathlib, but callers should still validate the final location before use.
    """
    p = Path(path_str)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def _safe_read(path: Path, max_bytes: int = MAX_FILE_SIZE) -> bytes:
    """Read a file with size limits and clear errors."""
    path = _resolve_path(str(path))
    if not path.exists():
        raise CLIError(f"file not found: {path}")
    if not path.is_file():
        raise CLIError(f"not a file: {path}")
    size = path.stat().st_size
    if size > max_bytes:
        raise CLIError(f"file too large: {path} ({size} bytes > {max_bytes})")
    return path.read_bytes()


def _atomic_write(path: Path, data: str | bytes, mode: int = 0o600) -> None:
    """Write data to a temporary file in the same directory, then rename atomically."""
    import contextlib

    path = _resolve_path(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        if isinstance(data, str):
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
        else:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        with contextlib.suppress(OSError):
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _load_ledger(path: Path) -> Ledger:
    """Load a ledger from JSON file with strict validation."""
    raw = _load_json(path)
    if raw.get("network_id") != NETWORK_ID:
        raise CLIError(f"invalid network ID: expected {NETWORK_ID}")
    if not isinstance(raw.get("chain"), list) or not raw["chain"]:
        raise CLIError("ledger must contain a non-empty chain")
    genesis_header = raw["chain"][0].get("header", {})
    if genesis_header.get("version") != PROTOCOL_VERSION:
        raise CLIError(f"invalid genesis protocol version: expected {PROTOCOL_VERSION}")
    if genesis_header.get("hash") != GENESIS_HASH and genesis_header.get("prev_hash") != "0" * 64:
        raise CLIError("ledger genesis does not match canonical v2 genesis")
    try:
        return Ledger.from_dict(raw)
    except (LedgerError, ValueError, KeyError, TypeError) as exc:
        raise CLIError(f"invalid ledger: {exc}") from exc


def _save_ledger(path: Path, ledger: Ledger) -> None:
    """Serialize a ledger to JSON atomically."""
    _atomic_write(path, json.dumps(ledger.to_dict(), indent=2), mode=0o644)


def _load_json(path: Path) -> dict[str, Any]:
    """Load and validate a JSON file, rejecting trailing bytes."""
    raw_bytes = _safe_read(path)
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CLIError(f"file is not valid UTF-8: {path}") from exc
    try:
        decoder = json.JSONDecoder()
        raw_text_stripped = raw_text.strip()
        raw, idx = decoder.raw_decode(raw_text_stripped)
    except json.JSONDecodeError as exc:
        raise CLIError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CLIError(f"expected JSON object in {path}")
    # Reject any trailing non-whitespace after the parsed JSON value.
    if idx < len(raw_text_stripped) and raw_text_stripped[idx:].strip():
        raise CLIError(f"trailing bytes after JSON value in {path}")
    return raw


def _load_private_key(path: Path) -> Any:
    """Load a raw 32-byte Ed25519 private key from a hex file."""
    try:
        return decode_private_key(_safe_read(path).decode("utf-8").strip())
    except Exception as exc:
        raise CLIError(f"invalid private key file {path}: {exc}") from exc


def _format_chain_work(work: int) -> str:
    """Format chain work as a readable integer string."""
    return str(work)


# ---------------------------------------------------------------------------
# v2 command group
# ---------------------------------------------------------------------------


@click.group(name="v2")
def v2() -> None:
    """Protocol v2 consensus and registry governance commands (alpha)."""


# ---------------------------------------------------------------------------
# v2 genesis
# ---------------------------------------------------------------------------


@v2.command(name="genesis")
def v2_genesis() -> None:
    """Display the fixed Protocol v2 genesis constants."""
    genesis = create_genesis_block()
    output = {
        "protocol_version": PROTOCOL_VERSION,
        "network_id": NETWORK_ID,
        "genesis_hash": GENESIS_HASH,
        "genesis_registry_root": GENESIS_REGISTRY_ROOT,
        "genesis_target": GENESIS_TARGET_HEX,
        "genesis_nonce": GENESIS_NONCE,
        "governance_threshold": GENESIS_THRESHOLD,
        "governance_public_keys": list(GENESIS_GOVERNANCE_KEYS),
        "genesis_block": genesis.to_dict(),
    }
    click.echo(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# v2 chain
# ---------------------------------------------------------------------------


@v2.group(name="chain")
def v2_chain() -> None:
    """Initialize and verify v2 ledgers."""


@v2_chain.command(name="init")
@click.option("--output", "-o", required=True, type=click.Path(), help="Ledger JSON output path")
@click.option("--force", is_flag=True, help="Overwrite an existing ledger file")
def v2_chain_init(output: str, force: bool) -> None:
    """Create a local v2 ledger initialized from the fixed genesis constants."""
    out_path = _resolve_path(output)
    if out_path.exists() and not force:
        raise CLIError(f"refusing to overwrite existing file: {out_path} (use --force)")

    ledger = Ledger()
    _save_ledger(out_path, ledger)
    click.echo(json.dumps({
        "path": str(out_path),
        "height": ledger.height(),
        "genesis_hash": ledger.genesis_hash(),
        "registry_root": GENESIS_REGISTRY_ROOT,
        "network_id": NETWORK_ID,
    }, indent=2))


@v2_chain.command(name="verify")
@click.option("--ledger", "-l", required=True, type=click.Path(), help="Ledger JSON file")
def v2_chain_verify(ledger: str) -> None:
    """Verify a serialized v2 ledger and report its state."""
    ledger_path = _resolve_path(ledger)
    try:
        led = _load_ledger(ledger_path)
    except CLIError:
        raise
    except Exception as exc:
        raise CLIError(f"failed to load ledger: {exc}") from exc

    valid = led.validate_chain()
    tip = led.last_block
    state = led.registry_state_at(led.height())

    output = {
        "valid": valid,
        "height": led.height(),
        "tip_hash": tip.hash,
        "chain_work": _format_chain_work(led.chain_work()),
        "registry_root": registry_root(state),
        "curator_count": len(state.records),
        "governance_threshold": led.governance_threshold,
        "governance_key_count": len(led.governance_keys),
    }
    click.echo(json.dumps(output, indent=2))

    if not valid:
        raise CLIError("ledger validation failed")


# ---------------------------------------------------------------------------
# v2 block
# ---------------------------------------------------------------------------


@v2.group(name="block")
def v2_block() -> None:
    """Mine and add v2 blocks."""


@v2_block.command(name="mine")
@click.option("--ledger", "-l", required=True, type=click.Path(), help="Input ledger JSON file")
@click.option("--transactions", "-t", type=click.Path(), help="JSON file with list of transactions")
@click.option("--timestamp", type=int, default=None, help="Block timestamp (Unix seconds)")
@click.option("--max-iters", type=int, default=10_000_000, help="Mining iteration limit")
@click.option("--output", "-o", required=True, type=click.Path(), help="Mined block JSON output path")
@click.option("--force", is_flag=True, help="Overwrite an existing block file")
def v2_block_mine(ledger: str, transactions: str | None, timestamp: int | None,
                  max_iters: int, output: str, force: bool) -> None:
    """Mine a non-genesis v2 block without modifying the ledger."""
    ledger_path = _resolve_path(ledger)
    out_path = _resolve_path(output)
    if out_path.exists() and not force:
        raise CLIError(f"refusing to overwrite existing file: {out_path} (use --force)")

    led = _load_ledger(ledger_path)
    initial_height = led.height()
    initial_tip = led.last_block.hash

    txs: list[dict[str, Any]] = []
    if transactions is not None:
        tx_data = _load_json(_resolve_path(transactions))
        if not isinstance(tx_data.get("transactions"), list):
            raise CLIError("transactions file must contain a 'transactions' list")
        txs = list(tx_data["transactions"])
        for tx in txs:
            if not isinstance(tx, dict):
                raise CLIError("all transactions must be JSON objects")

    try:
        block = led.mine_block_v2(txs, max_iterations=max_iters, timestamp=timestamp)
    except LedgerError as exc:
        raise CLIError(f"mining failed: {exc}") from exc

    # Ensure the ledger was never mutated by mining.
    if led.height() != initial_height or led.last_block.hash != initial_tip:
        raise CLIError("ledger was unexpectedly mutated during mining")

    _atomic_write(out_path, json.dumps(block.to_dict(), indent=2), mode=0o644)
    click.echo(json.dumps({
        "path": str(out_path),
        "height": led.height() + 1,
        "hash": block.hash,
        "registry_root": block.header.registry_root,
        "target": target_to_hex(block.header.target),
        "nonce": block.header.nonce,
        "transaction_count": len(block.transactions),
    }, indent=2))


@v2_block.command(name="add")
@click.option("--ledger", "-l", required=True, type=click.Path(), help="Ledger JSON file to update")
@click.option("--block", "-b", required=True, type=click.Path(), help="Block JSON file to add")
@click.option("--output", "-o", type=click.Path(), help="Updated ledger output path (defaults to --ledger)")
@click.option("--force", is_flag=True, help="Overwrite output file if it exists")
def v2_block_add(ledger: str, block: str, output: str | None, force: bool) -> None:
    """Add a mined block to a ledger after full consensus validation."""
    ledger_path = _resolve_path(ledger)
    block_path = _resolve_path(block)
    out_path = _resolve_path(output) if output else ledger_path

    if out_path.exists() and not force and out_path != ledger_path:
        raise CLIError(f"refusing to overwrite existing file: {out_path} (use --force)")

    led = _load_ledger(ledger_path)

    block_data = _load_json(block_path)
    try:
        new_block = BlockV2.from_dict(block_data)
    except (KeyError, ValueError, TypeError) as exc:
        raise CLIError(f"invalid block: {exc}") from exc

    # Explicit structural checks for clear error messages.
    expected_height = led.height() + 1
    if new_block.header.version != PROTOCOL_VERSION:
        raise CLIError(f"invalid block protocol version: expected {PROTOCOL_VERSION}")
    if new_block.header.prev_hash != led.last_block.hash:
        raise CLIError("block previous hash does not match ledger tip")
    if new_block.header.target != led.expected_target_at(expected_height):
        raise CLIError("block target does not match expected difficulty")
    previous_state = led._state_at(expected_height - 1)
    expected_registry_root = registry_root(previous_state)
    if new_block.header.registry_root != expected_registry_root:
        raise CLIError("block registry root does not match expected state")

    # Full consensus validation before mutating the ledger.
    if not led.add_block_v2(new_block):
        raise CLIError("block rejected by consensus validation")

    _save_ledger(out_path, led)
    state = led.registry_state_at(led.height())
    click.echo(json.dumps({
        "height": led.height(),
        "tip_hash": led.last_block.hash,
        "registry_root": registry_root(state),
        "curator_count": len(state.records),
        "chain_work": _format_chain_work(led.chain_work()),
        "path": str(out_path),
    }, indent=2))


# ---------------------------------------------------------------------------
# v2 curator
# ---------------------------------------------------------------------------


@v2.group(name="curator")
def v2_curator() -> None:
    """Curator key management for v2 attestations."""


@v2_curator.command(name="generate")
@click.option("--private-key", "-k", required=True, type=click.Path(), help="Output path for the private key")
@click.option("--public-key", "-p", type=click.Path(), help="Optional output path for the public key")
@click.option("--force", is_flag=True, help="Overwrite existing key files")
def v2_curator_generate(private_key: str, public_key: str | None, force: bool) -> None:
    """Generate an Ed25519 curator keypair."""
    sk_path = _resolve_path(private_key)
    if sk_path.exists() and not force:
        raise CLIError(f"refusing to overwrite private key: {sk_path} (use --force)")

    sk, pk = generate_keypair()
    sk_hex = sk.private_bytes_raw().hex()
    pk_hex = encode_public_key(pk)

    _atomic_write(sk_path, sk_hex + "\n", mode=0o600)

    output = {
        "private_key_path": str(sk_path),
        "public_key_hex": pk_hex,
    }

    if public_key is not None:
        pk_path = _resolve_path(public_key)
        if pk_path.exists() and not force:
            raise CLIError(f"refusing to overwrite public key: {pk_path} (use --force)")
        _atomic_write(pk_path, pk_hex + "\n", mode=0o644)
        output["public_key_path"] = str(pk_path)

    click.echo(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# v2 governance
# ---------------------------------------------------------------------------


@v2.group(name="governance")
def v2_governance() -> None:
    """Build and sign registry governance transactions."""


def _load_governance_keys(key_paths: list[str]) -> list[Any]:
    """Load private keys used to sign governance transactions."""
    keys = []
    for path_str in key_paths:
        path = _resolve_path(path_str)
        keys.append(_load_private_key(path))
    return keys


def _tx_body_to_envelope(body: dict[str, Any]) -> dict[str, Any]:
    """Wrap a governance transaction body in the canonical envelope."""
    return {"type": "governance", "body": body}


@v2_governance.command(name="register")
@click.option("--curator-id", required=True, help="New curator identifier")
@click.option("--public-key", required=True, help="Curator public key hex (64 characters)")
@click.option("--activation-height", required=True, type=int, help="Block height at which key becomes active")
@click.option("--previous-registry-root", required=True, help="Registry root before this transaction")
@click.option("--governance-key", "governance_keys", multiple=True, required=True, help="Path to a governance private key file")
@click.option("--key-index", "key_indices", multiple=True, type=int, required=True, help="Governance key index for each signature")
@click.option("--output", "-o", required=True, type=click.Path(), help="Transaction JSON output path")
@click.option("--force", is_flag=True, help="Overwrite output file")
def v2_governance_register(
    curator_id: str,
    public_key: str,
    activation_height: int,
    previous_registry_root: str,
    governance_keys: tuple[str, ...],
    key_indices: tuple[int, ...],
    output: str,
    force: bool,
) -> None:
    """Build and sign a curator registration transaction."""
    _build_sign_governance_tx(
        action="curator_register",
        curator_id=curator_id,
        public_key=public_key,
        activation_height=activation_height,
        previous_registry_root=previous_registry_root,
        governance_keys=list(governance_keys),
        key_indices=list(key_indices),
        output=output,
        force=force,
    )


@v2_governance.command(name="rotate")
@click.option("--curator-id", required=True, help="Curator identifier")
@click.option("--public-key", required=True, help="Current curator public key hex")
@click.option("--new-public-key", required=True, help="New curator public key hex")
@click.option("--activation-height", required=True, type=int, help="Height at which new key becomes active")
@click.option("--previous-registry-root", required=True, help="Registry root before this transaction")
@click.option("--governance-key", "governance_keys", multiple=True, required=True, help="Path to governance private key files")
@click.option("--key-index", "key_indices", multiple=True, type=int, required=True, help="Governance key index for each signature")
@click.option("--curator-private-key", required=True, type=click.Path(), help="Current curator private key file")
@click.option("--output", "-o", required=True, type=click.Path(), help="Transaction JSON output path")
@click.option("--force", is_flag=True, help="Overwrite output file")
def v2_governance_rotate(
    curator_id: str,
    public_key: str,
    new_public_key: str,
    activation_height: int,
    previous_registry_root: str,
    governance_keys: tuple[str, ...],
    key_indices: tuple[int, ...],
    curator_private_key: str,
    output: str,
    force: bool,
) -> None:
    """Build and sign a curator rotation transaction."""
    _build_sign_governance_tx(
        action="curator_rotate",
        curator_id=curator_id,
        public_key=public_key,
        new_public_key=new_public_key,
        activation_height=activation_height,
        previous_registry_root=previous_registry_root,
        governance_keys=list(governance_keys),
        key_indices=list(key_indices),
        curator_private_key=curator_private_key,
        output=output,
        force=force,
    )


@v2_governance.command(name="revoke")
@click.option("--curator-id", required=True, help="Curator identifier")
@click.option("--public-key", required=True, help="Current curator public key hex")
@click.option("--revocation-height", required=True, type=int, help="Height at which key is revoked")
@click.option("--reason", required=True, help="Revocation reason code")
@click.option("--previous-registry-root", required=True, help="Registry root before this transaction")
@click.option("--governance-key", "governance_keys", multiple=True, required=True, help="Path to governance private key files")
@click.option("--key-index", "key_indices", multiple=True, type=int, required=True, help="Governance key index for each signature")
@click.option("--curator-private-key", required=True, type=click.Path(), help="Current curator private key file")
@click.option("--output", "-o", required=True, type=click.Path(), help="Transaction JSON output path")
@click.option("--force", is_flag=True, help="Overwrite output file")
def v2_governance_revoke(
    curator_id: str,
    public_key: str,
    revocation_height: int,
    reason: str,
    previous_registry_root: str,
    governance_keys: tuple[str, ...],
    key_indices: tuple[int, ...],
    curator_private_key: str,
    output: str,
    force: bool,
) -> None:
    """Build and sign a curator revocation transaction."""
    _build_sign_governance_tx(
        action="curator_revoke",
        curator_id=curator_id,
        public_key=public_key,
        revocation_height=revocation_height,
        reason=reason,
        previous_registry_root=previous_registry_root,
        governance_keys=list(governance_keys),
        key_indices=list(key_indices),
        curator_private_key=curator_private_key,
        output=output,
        force=force,
    )


def _build_sign_governance_tx(
    action: str,
    curator_id: str,
    public_key: str,
    previous_registry_root: str,
    governance_keys: list[str],
    key_indices: list[int],
    output: str,
    force: bool,
    activation_height: int | None = None,
    new_public_key: str | None = None,
    revocation_height: int | None = None,
    reason: str | None = None,
    curator_private_key: str | None = None,
) -> None:
    """Shared implementation for register/rotate/revoke governance commands."""
    out_path = _resolve_path(output)
    if out_path.exists() and not force:
        raise CLIError(f"refusing to overwrite existing file: {out_path} (use --force)")

    if len(governance_keys) != len(key_indices):
        raise CLIError("each --governance-key must have a matching --key-index")

    priv_keys = _load_governance_keys(governance_keys)

    body: dict[str, Any] = {
        "action": action,
        "curator_id": curator_id,
        "public_key_hex": public_key,
        "previous_registry_root": previous_registry_root,
    }
    if action == "curator_register":
        body["activation_height"] = activation_height
    elif action == "curator_rotate":
        body["activation_height"] = activation_height
        body["new_public_key_hex"] = new_public_key
    elif action == "curator_revoke":
        body["revocation_height"] = revocation_height
        body["reason_code"] = reason

    # Add curator signature for rotate/revoke
    if action in ("curator_rotate", "curator_revoke"):
        if curator_private_key is None:
            raise CLIError(f"--curator-private-key is required for {action}")
        curator_sk = _load_private_key(_resolve_path(curator_private_key))
        body["curator_signature"] = make_curator_signature(curator_sk, body)

    # Governance signatures in provided order; canonical txid will sort them.
    sigs = []
    for sk, idx in zip(priv_keys, key_indices):
        sigs.append(make_governance_signature(sk, body, idx))
    body["governance_signatures"] = [s.to_dict() for s in sigs]

    envelope = _tx_body_to_envelope(body)
    _atomic_write(out_path, json.dumps(envelope, indent=2), mode=0o644)
    click.echo(json.dumps({
        "path": str(out_path),
        "action": action,
        "curator_id": curator_id,
        "canonical_txid": _canonical_txid(body),
    }, indent=2))


def _canonical_txid(body: dict[str, Any]) -> str:
    """Return deterministic transaction ID with canonical signature ordering."""
    from .chain import _canonical_txid as chain_canonical_txid
    return chain_canonical_txid(body)


# ---------------------------------------------------------------------------
# v2 attest
# ---------------------------------------------------------------------------


@v2.group(name="attest")
def v2_attest() -> None:
    """Create and verify historical archive attestations."""


@v2_attest.command(name="create")
@click.option("--body-hash", required=True, help="Manifest hash to attest")
@click.option("--curator-id", required=True, help="Curator identifier")
@click.option("--block-height", required=True, type=int, help="Attestation block height")
@click.option("--private-key", required=True, type=click.Path(), help="Curator private key file")
@click.option("--output", "-o", required=True, type=click.Path(), help="Attestation JSON output path")
@click.option("--force", is_flag=True, help="Overwrite output file")
def v2_attest_create(
    body_hash: str,
    curator_id: str,
    block_height: int,
    private_key: str,
    output: str,
    force: bool,
) -> None:
    """Create a v2 historical archive attestation."""
    out_path = _resolve_path(output)
    if out_path.exists() and not force:
        raise CLIError(f"refusing to overwrite existing file: {out_path} (use --force)")

    sk = _load_private_key(_resolve_path(private_key))
    pk_hex = encode_public_key(sk.public_key())
    witness = sign_attestation_v2(sk, body_hash, curator_id, block_height)
    witness["public_key_hex"] = pk_hex

    _atomic_write(out_path, json.dumps(witness, indent=2), mode=0o644)
    click.echo(json.dumps({
        "path": str(out_path),
        "curator_id": curator_id,
        "block_height": block_height,
        "public_key_hex": pk_hex,
    }, indent=2))


@v2_attest.command(name="verify")
@click.option("--ledger", "-l", required=True, type=click.Path(), help="Ledger JSON file")
@click.option("--body-hash", required=True, help="Manifest hash that was attested")
@click.option("--attestation", "-a", required=True, type=click.Path(), help="Attestation JSON file")
@click.option("--block-height", required=True, type=int, help="Expected attestation block height")
def v2_attest_verify(
    ledger: str,
    body_hash: str,
    attestation: str,
    block_height: int,
) -> None:
    """Verify an attestation against registry state at the specified height."""
    led = _load_ledger(_resolve_path(ledger))
    try:
        state = led.registry_state_at(block_height)
    except LedgerError as exc:
        raise CLIError(f"invalid block height: {exc}") from exc

    witness = _load_json(_resolve_path(attestation))
    valid = verify_attestation_v2(state, witness, body_hash, block_height)
    click.echo(json.dumps({
        "valid": valid,
        "curator_id": witness.get("curator_id"),
        "block_height": block_height,
        "body_hash": body_hash,
    }, indent=2))
    if not valid:
        raise CLIError("attestation verification failed")


# ---------------------------------------------------------------------------
# v2 archive
# ---------------------------------------------------------------------------


@v2.group(name="archive")
def v2_archive() -> None:
    """Create and verify canonical archive manifests."""


@v2_archive.command(name="add")
@click.option("--data-dir", required=True, type=click.Path(), help="Archive base directory")
@click.option("--file", "input_file", required=True, type=click.Path(), help="Document to archive")
@click.option("--title", required=True, help="Document title")
@click.option("--media-type", default="application/octet-stream", help="Media type")
@click.option("--language", default=None, help="Language code")
@click.option("--source", default=None, help="Source description")
@click.option("--source-uri", default=None, help="Source URI")
@click.option("--license", default=None, help="Rights/license status")
@click.option("--output-manifest", "-o", type=click.Path(), help="Optional manifest JSON output path")
@click.option("--force", is_flag=True, help="Overwrite output files")
def v2_archive_add(
    data_dir: str,
    input_file: str,
    title: str,
    media_type: str,
    language: str | None,
    source: str | None,
    source_uri: str | None,
    license: str | None,
    output_manifest: str | None,
    force: bool,
) -> None:
    """Create and store a canonical archive manifest."""
    base = _resolve_path(data_dir)
    in_path = _resolve_path(input_file)

    archive = Archive(str(base))
    data = _safe_read(in_path)
    manifest_hash = archive.add_document(
        data,
        title=title,
        media_type=media_type,
        language=language,
        source=source,
        source_uri=source_uri,
        license=license,
    )
    manifest = archive.get_manifest(manifest_hash)

    if output_manifest is not None:
        out_path = _resolve_path(output_manifest)
        if out_path.exists() and not force:
            raise CLIError(f"refusing to overwrite existing file: {out_path} (use --force)")
        _atomic_write(out_path, json.dumps(manifest, indent=2, ensure_ascii=False), mode=0o644)

    click.echo(json.dumps({
        "manifest_hash": manifest_hash,
        "content_hash": manifest["content_hash"],
        "byte_length": manifest["byte_length"],
        "media_type": manifest["media_type"],
        "title": manifest["title"],
    }, indent=2))


@v2_archive.command(name="verify")
@click.option("--data-dir", required=True, type=click.Path(), help="Archive base directory")
@click.option("--manifest-hash", required=True, help="Manifest hash to verify")
def v2_archive_verify(
    data_dir: str,
    manifest_hash: str,
) -> None:
    """Verify stored manifest and content integrity."""
    base = _resolve_path(data_dir)
    archive = Archive(str(base))

    manifest_ok = archive.verify_manifest(manifest_hash)
    if not manifest_ok:
        raise CLIError("manifest verification failed")

    try:
        manifest = archive.get_manifest(manifest_hash)
        content = archive.get_document(manifest["content_hash"])
    except Exception as exc:
        raise CLIError(f"content verification failed: {exc}") from exc

    click.echo(json.dumps({
        "manifest_hash": manifest_hash,
        "manifest_valid": True,
        "content_hash": manifest["content_hash"],
        "byte_length": len(content),
        "title": manifest["title"],
    }, indent=2))
