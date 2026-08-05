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
    HashEngine,
    decode_private_key,
    decode_public_key,
    encode_public_key,
    generate_keypair,
    make_curator_signature,
    target_to_hex,
)
from .governance import (
    GOVERNANCE_SCHEMA_VERSION,
    GovernanceContext,
    GovernanceError,
    make_governance_signature,
)
from .registry_state import (
    RegistryError,
    RegistryState,
    registry_root,
)
from .witness import sign_attestation_v2, verify_attestation_v2

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
ALPHA_MAX_FILE_SIZE = 1 * 1024 * 1024 * 1024  # 1 GB soft ceiling for alpha usage


def _stream_hash(path: Path, max_bytes: int = ALPHA_MAX_FILE_SIZE) -> tuple[str, int]:
    """Return (sha256_hex, byte_length) reading the file in chunks.

    This avoids loading unbounded files entirely into memory.
    """
    import hashlib

    path = _resolve_path(str(path))
    if not path.exists():
        raise CLIError(f"file not found: {path}")
    if not path.is_file():
        raise CLIError(f"not a file: {path}")
    size = path.stat().st_size
    if size > max_bytes:
        raise CLIError(
            f"file too large: {path} ({size} bytes > {max_bytes}). "
            "Alpha supports files up to 1 GB; contact operators for larger archives."
        )
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest(), size


def _is_path_traversal(target: Path, base: Path) -> bool:
    """Return True if target resolves outside base."""
    try:
        target.resolve().relative_to(base.resolve())
        return False
    except ValueError:
        return True




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
        if isinstance(tx_data, list):
            txs = list(tx_data)
        elif isinstance(tx_data, dict):
            if "transactions" in tx_data and isinstance(tx_data["transactions"], list):
                txs = list(tx_data["transactions"])
            else:
                # Single transaction envelope, e.g. the output of v2 governance commands.
                txs = [tx_data]
        else:
            raise CLIError("transactions file must contain a JSON object or a list of transactions")
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
@click.option("--curator-id", help="Curator identifier (user-assigned, echoed in output)")
@click.option("--private-key", "-k", required=True, type=click.Path(), help="Output path for the private key")
@click.option("--public-key", "-p", type=click.Path(), help="Optional output path for the public key")
@click.option("--force", is_flag=True, help="Overwrite existing key files")
def v2_curator_generate(curator_id: str | None, private_key: str, public_key: str | None, force: bool) -> None:
    """Generate an Ed25519 curator keypair.

    The private key is written atomically with restrictive permissions (0o600
    on POSIX). It is never printed, logged, or returned as JSON. Only the
    curator identifier and the public key hex are emitted.
    """
    sk_path = _resolve_path(private_key)
    if sk_path.exists() and not force:
        raise CLIError(f"refusing to overwrite private key: {sk_path} (use --force)")

    sk, pk = generate_keypair()
    sk_hex = sk.private_bytes_raw().hex()
    pk_hex = encode_public_key(pk)

    _atomic_write(sk_path, sk_hex + "\n", mode=0o600)

    output: dict[str, Any] = {
        "public_key_hex": pk_hex,
    }
    if curator_id is not None:
        output["curator_id"] = curator_id

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


def _derive_previous_registry_root(ledger: Ledger) -> str:
    """Return the registry root committed to by the next block."""
    return registry_root(ledger.registry_state_at(ledger.height()))


def _candidate_block_height(ledger: Ledger) -> int:
    """Return the height of the block that would include a new transaction."""
    return ledger.height() + 1


@v2_governance.command(name="register")
@click.option("--ledger", "-l", required=True, type=click.Path(), help="Ledger JSON file")
@click.option("--curator-id", required=True, help="New curator identifier")
@click.option("--public-key", required=True, help="Curator public key hex (64 characters)")
@click.option("--activation-height", required=True, type=int, help="Block height at which key becomes active")
@click.option("--governance-key", "governance_keys", multiple=True, required=True, help="Path to a governance private key file")
@click.option("--key-index", "key_indices", multiple=True, type=int, required=True, help="Governance key index for each signature")
@click.option("--output", "-o", required=True, type=click.Path(), help="Transaction JSON output path")
@click.option("--force", is_flag=True, help="Overwrite output file")
def v2_governance_register(
    ledger: str,
    curator_id: str,
    public_key: str,
    activation_height: int,
    governance_keys: tuple[str, ...],
    key_indices: tuple[int, ...],
    output: str,
    force: bool,
) -> None:
    """Build and sign a curator registration transaction."""
    _build_sign_governance_tx(
        action="curator_register",
        ledger_path=ledger,
        curator_id=curator_id,
        public_key=public_key,
        activation_height=activation_height,
        governance_keys=list(governance_keys),
        key_indices=list(key_indices),
        output=output,
        force=force,
    )


@v2_governance.command(name="rotate")
@click.option("--ledger", "-l", required=True, type=click.Path(), help="Ledger JSON file")
@click.option("--curator-id", required=True, help="Curator identifier")
@click.option("--public-key", required=True, help="Current curator public key hex")
@click.option("--new-public-key", required=True, help="New curator public key hex")
@click.option("--activation-height", required=True, type=int, help="Height at which new key becomes active")
@click.option("--governance-key", "governance_keys", multiple=True, required=True, help="Path to governance private key files")
@click.option("--key-index", "key_indices", multiple=True, type=int, required=True, help="Governance key index for each signature")
@click.option("--curator-private-key", required=True, type=click.Path(), help="Current curator private key file")
@click.option("--output", "-o", required=True, type=click.Path(), help="Transaction JSON output path")
@click.option("--force", is_flag=True, help="Overwrite output file")
def v2_governance_rotate(
    ledger: str,
    curator_id: str,
    public_key: str,
    new_public_key: str,
    activation_height: int,
    governance_keys: tuple[str, ...],
    key_indices: tuple[int, ...],
    curator_private_key: str,
    output: str,
    force: bool,
) -> None:
    """Build and sign a curator rotation transaction."""
    _build_sign_governance_tx(
        action="curator_rotate",
        ledger_path=ledger,
        curator_id=curator_id,
        public_key=public_key,
        new_public_key=new_public_key,
        activation_height=activation_height,
        governance_keys=list(governance_keys),
        key_indices=list(key_indices),
        curator_private_key=curator_private_key,
        output=output,
        force=force,
    )


@v2_governance.command(name="revoke")
@click.option("--ledger", "-l", required=True, type=click.Path(), help="Ledger JSON file")
@click.option("--curator-id", required=True, help="Curator identifier")
@click.option("--public-key", required=True, help="Current curator public key hex")
@click.option("--revocation-height", required=True, type=int, help="Height at which key is revoked")
@click.option("--reason", required=True, help="Revocation reason code")
@click.option("--governance-key", "governance_keys", multiple=True, required=True, help="Path to governance private key files")
@click.option("--key-index", "key_indices", multiple=True, type=int, required=True, help="Governance key index for each signature")
@click.option("--curator-private-key", required=True, type=click.Path(), help="Current curator private key file")
@click.option("--output", "-o", required=True, type=click.Path(), help="Transaction JSON output path")
@click.option("--force", is_flag=True, help="Overwrite output file")
def v2_governance_revoke(
    ledger: str,
    curator_id: str,
    public_key: str,
    revocation_height: int,
    reason: str,
    governance_keys: tuple[str, ...],
    key_indices: tuple[int, ...],
    curator_private_key: str,
    output: str,
    force: bool,
) -> None:
    """Build and sign a curator revocation transaction."""
    _build_sign_governance_tx(
        action="curator_revoke",
        ledger_path=ledger,
        curator_id=curator_id,
        public_key=public_key,
        revocation_height=revocation_height,
        reason=reason,
        governance_keys=list(governance_keys),
        key_indices=list(key_indices),
        curator_private_key=curator_private_key,
        output=output,
        force=force,
    )


def _build_sign_governance_tx(
    action: str,
    ledger_path: str,
    curator_id: str,
    public_key: str,
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
    if not governance_keys:
        raise CLIError("at least one --governance-key is required")

    led = _load_ledger(_resolve_path(ledger_path))
    candidate_height = _candidate_block_height(led)
    previous_registry_root = _derive_previous_registry_root(led)
    state = led.registry_state_at(led.height())

    # Validate public key format early with a clear error.
    try:
        decode_public_key(public_key)
    except Exception as exc:
        raise CLIError(f"invalid public key: {exc}") from exc

    body: dict[str, Any] = {
        "action": action,
        "curator_id": curator_id,
        "public_key_hex": public_key,
        "previous_registry_root": previous_registry_root,
        "network_id": NETWORK_ID,
        "schema_version": GOVERNANCE_SCHEMA_VERSION,
    }

    if action == "curator_register":
        if activation_height is None:
            raise CLIError("--activation-height is required for curator_register")
        if activation_height <= candidate_height:
            raise CLIError(
                f"activation_height ({activation_height}) must be greater than "
                f"candidate block height ({candidate_height})"
            )
        body["activation_height"] = activation_height
        # Reject registering an already-used curator id or public key.
        for record in state.records:
            if record.curator_id == curator_id:
                raise CLIError(f"curator_id {curator_id!r} is already registered")
            if record.public_key_hex == public_key:
                raise CLIError(f"public key is already registered under {record.curator_id!r}")

    elif action == "curator_rotate":
        if activation_height is None:
            raise CLIError("--activation-height is required for curator_rotate")
        if new_public_key is None:
            raise CLIError("--new-public-key is required for curator_rotate")
        if activation_height <= candidate_height:
            raise CLIError(
                f"activation_height ({activation_height}) must be greater than "
                f"candidate block height ({candidate_height})"
            )
        body["activation_height"] = activation_height
        body["new_public_key_hex"] = new_public_key
        _require_active_curator_key(state, curator_id, public_key)
        try:
            decode_public_key(new_public_key)
        except Exception as exc:
            raise CLIError(f"invalid new public key: {exc}") from exc
        for record in state.records:
            if record.public_key_hex == new_public_key and record.curator_id != curator_id:
                raise CLIError(f"new public key is already registered under {record.curator_id!r}")

    elif action == "curator_revoke":
        if revocation_height is None:
            raise CLIError("--revocation-height is required for curator_revoke")
        if reason is None:
            raise CLIError("--reason is required for curator_revoke")
        if revocation_height <= candidate_height:
            raise CLIError(
                f"revocation_height ({revocation_height}) must be greater than "
                f"candidate block height ({candidate_height})"
            )
        body["revocation_height"] = revocation_height
        body["reason_code"] = reason
        record = _require_active_curator_key(state, curator_id, public_key)
        if record.revocation_height is not None:
            raise CLIError("curator is already revoked")
        if revocation_height < record.activation_height:
            raise CLIError(
                f"revocation_height ({revocation_height}) must be >= "
                f"activation_height ({record.activation_height})"
            )

    # Add curator signature for rotate/revoke.
    if action in ("curator_rotate", "curator_revoke"):
        if curator_private_key is None:
            raise CLIError(f"--curator-private-key is required for {action}")
        curator_sk = _load_private_key(_resolve_path(curator_private_key))
        # The curator signs the body without any witness fields.
        body_without_curator = {k: v for k, v in body.items() if k not in {"governance_signatures", "curator_signature"}}
        body["curator_signature"] = make_curator_signature(curator_sk, body_without_curator)

    # Governance signatures in provided order; the body written to disk will sort them canonically.
    priv_keys = _load_governance_keys(governance_keys)
    seen_indices: set[int] = set()
    sigs = []
    for sk, idx in zip(priv_keys, key_indices):
        if idx in seen_indices:
            raise CLIError(f"duplicate governance key index: {idx}")
        seen_indices.add(idx)
        if idx < 0 or idx >= len(led.governance_keys):
            raise CLIError(f"governance key index {idx} out of range (0..{len(led.governance_keys) - 1})")
        # Sign over the body without any witness fields to match the ledger reducer.
        body_without_witness = {k: v for k, v in body.items() if k not in {"governance_signatures", "curator_signature"}}
        sigs.append(make_governance_signature(sk, body_without_witness, idx))

    # Canonical ordering by key_index.
    body["governance_signatures"] = [s.to_dict() for s in sorted(sigs, key=lambda s: s.key_index)]

    # Verify the assembled transaction against the ledger's governance context. This catches
    # insufficient, malformed, or invalid signatures before any output is written.
    try:
        ctx = GovernanceContext(led.governance_keys, led.governance_threshold)
        _validate_governance_body(body, ctx)
    except (GovernanceError, RegistryError) as exc:
        raise CLIError(f"governance authorization failed: {exc}") from exc

    envelope = _tx_body_to_envelope(body)
    _atomic_write(out_path, json.dumps(envelope, indent=2), mode=0o644)
    click.echo(json.dumps({
        "path": str(out_path),
        "action": action,
        "curator_id": curator_id,
        "canonical_txid": _canonical_txid(body),
        "previous_registry_root": previous_registry_root,
    }, indent=2))


def _require_active_curator_key(state: RegistryState, curator_id: str, public_key_hex: str) -> Any:
    """Return the active curator record matching curator_id and public_key_hex."""
    matches = [r for r in state.records if r.curator_id == curator_id]
    if not matches:
        raise CLIError(f"unknown curator {curator_id!r}")
    # Use the latest record for this curator id (highest activation height).
    record = max(matches, key=lambda r: r.activation_height)
    if record.public_key_hex != public_key_hex:
        raise CLIError("public_key_hex does not match active record")
    if record.revocation_height is not None:
        raise CLIError("curator is already revoked")
    return record


def _validate_governance_body(body: dict[str, Any], context: GovernanceContext) -> None:
    """Run the same validation the ledger reducer performs on the assembled body."""
    from .governance import (
        CuratorRegisterTx,
        CuratorRevokeTx,
        CuratorRotateTx,
    )

    action = body["action"]
    tx: CuratorRegisterTx | CuratorRotateTx | CuratorRevokeTx
    if action == "curator_register":
        tx = CuratorRegisterTx.from_dict(body)
    elif action == "curator_rotate":
        tx = CuratorRotateTx.from_dict(body)
    elif action == "curator_revoke":
        tx = CuratorRevokeTx.from_dict(body)
    else:
        raise CLIError(f"unsupported governance action: {action}")

    tx_dict = tx.to_dict()
    witness_keys = {"governance_signatures"}
    if action in ("curator_rotate", "curator_revoke"):
        witness_keys.add("curator_signature")
    body_without_witness = {k: v for k, v in tx_dict.items() if k not in witness_keys}
    context.verify_governance_signatures(body_without_witness, tx.governance_signatures)



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
@click.option("--ledger", "-l", required=True, type=click.Path(), help="Ledger JSON file")
@click.option("--manifest", "-m", required=True, type=click.Path(), help="Manifest JSON file or manifest hash")
@click.option("--curator-id", required=True, help="Curator identifier")
@click.option("--block-height", required=True, type=int, help="Attestation block height")
@click.option("--private-key", required=True, type=click.Path(), help="Curator private key file")
@click.option("--output", "-o", required=True, type=click.Path(), help="Attestation JSON output path")
@click.option("--force", is_flag=True, help="Overwrite output file")
def v2_attest_create(
    ledger: str,
    manifest: str,
    curator_id: str,
    block_height: int,
    private_key: str,
    output: str,
    force: bool,
) -> None:
    """Create a v2 historical archive attestation.

    The curator key must be active at the requested block height. The manifest
    argument may be a manifest JSON file (its body hash is computed) or a bare
    64-character manifest hash.
    """
    out_path = _resolve_path(output)
    if out_path.exists() and not force:
        raise CLIError(f"refusing to overwrite existing file: {out_path} (use --force)")

    led = _load_ledger(_resolve_path(ledger))
    try:
        state = led.registry_state_at(block_height)
    except LedgerError as exc:
        raise CLIError(f"invalid block height: {exc}") from exc

    manifest_path = _resolve_path(manifest)
    if manifest_path.exists() and manifest_path.is_file():
        manifest_data = _load_json(manifest_path)
        body = manifest_data.get("body", manifest_data)
        body_hash = HashEngine.hash_object_hex(body)
    elif len(manifest) == 64 and all(c in "0123456789abcdef" for c in manifest.lower()):
        body_hash = manifest.lower()
    else:
        raise CLIError("manifest must be a manifest JSON file path or a 64-character hex hash")

    sk = _load_private_key(_resolve_path(private_key))
    pk_hex = encode_public_key(sk.public_key())
    if not state.key_was_valid_at(curator_id, pk_hex, block_height):
        raise CLIError(f"curator {curator_id!r} public key is not active at block height {block_height}")

    witness = sign_attestation_v2(sk, body_hash, curator_id, block_height)
    witness["public_key_hex"] = pk_hex

    _atomic_write(out_path, json.dumps(witness, indent=2), mode=0o644)
    click.echo(json.dumps({
        "path": str(out_path),
        "curator_id": curator_id,
        "block_height": block_height,
        "body_hash": body_hash,
        "public_key_hex": pk_hex,
    }, indent=2))


@v2_attest.command(name="verify")
@click.option("--ledger", "-l", required=True, type=click.Path(), help="Ledger JSON file")
@click.option("--attestation", "-a", required=True, type=click.Path(), help="Attestation JSON file")
@click.option("--manifest", "-m", required=True, help="Manifest JSON file path or manifest hash")
@click.option("--block-height", required=True, type=int, help="Expected attestation block height")
def v2_attest_verify(
    ledger: str,
    attestation: str,
    manifest: str,
    block_height: int,
) -> None:
    """Verify a v2 historical attestation against registry state at the specified height.

    Historical validity is evaluated at block_height, independent of the current
    wall clock.
    """
    led = _load_ledger(_resolve_path(ledger))
    try:
        state = led.registry_state_at(block_height)
    except LedgerError as exc:
        raise CLIError(f"invalid block height: {exc}") from exc

    witness_path = _resolve_path(attestation)
    witness = _load_json(witness_path)

    manifest_path = _resolve_path(manifest)
    if manifest_path.exists() and manifest_path.is_file():
        manifest_data = _load_json(manifest_path)
        body = manifest_data.get("body", manifest_data)
        body_hash = HashEngine.hash_object_hex(body)
    elif len(manifest) == 64 and all(c in "0123456789abcdef" for c in manifest.lower()):
        body_hash = manifest.lower()
    else:
        raise CLIError("manifest must be a manifest JSON file path or a 64-character hex hash")

    # Reject duplicate/malformed attestations cleanly.
    if not isinstance(witness, dict):
        raise CLIError("attestation must be a JSON object")
    for key in ("curator_id", "block_height", "signature", "public_key_hex"):
        if key not in witness:
            raise CLIError(f"attestation missing required field: {key}")

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
@click.option("--source-identifier", default=None, help="Source identifier or URI")
@click.option("--source-uri", default=None, help="Source URI (legacy alias for --source-identifier)")
@click.option("--acquisition-date", type=int, default=None, help="Acquisition date as Unix timestamp")
@click.option("--license", default=None, help="Rights/license status")
@click.option("--parent-hash", default=None, help="Previous-version content hash")
@click.option("--metadata", type=click.Path(), default=None, help="Optional JSON metadata file")
@click.option("--notes", type=click.Path(), default=None, help="Optional notes file")
@click.option("--output-manifest", "-o", type=click.Path(), help="Optional manifest JSON output path")
@click.option("--force", is_flag=True, help="Overwrite output files")
def v2_archive_add(
    data_dir: str,
    input_file: str,
    title: str,
    media_type: str,
    language: str | None,
    source: str | None,
    source_identifier: str | None,
    source_uri: str | None,
    acquisition_date: int | None,
    license: str | None,
    parent_hash: str | None,
    metadata: str | None,
    notes: str | None,
    output_manifest: str | None,
    force: bool,
) -> None:
    """Create and store a canonical chainbreaker-manifest-v1 archive manifest.

    The document bytes are hashed with streaming SHA-256 so unbounded files are
    never loaded entirely into memory. Alpha usage is soft-capped at 1 GB.
    """
    base = _resolve_path(data_dir)
    in_path = _resolve_path(input_file)
    # Reject relative paths that try to escape the current working directory.
    for raw_path in (data_dir, input_file):
        p_raw = Path(raw_path)
        if not p_raw.is_absolute() and any(part == ".." for part in p_raw.parts):
            raise CLIError("path traversal is not allowed")

    content_hash, byte_length = _stream_hash(in_path)

    # Optional metadata and notes files are read as opaque byte blobs; only their
    # hashes are recorded in the manifest.
    metadata_hash: str | None = None
    if metadata is not None:
        metadata_path = _resolve_path(metadata)
        if _is_path_traversal(metadata_path, base):
            raise CLIError("path traversal is not allowed")
        metadata_bytes = _safe_read(metadata_path)
        metadata_hash = HashEngine.hash_single_hex(metadata_bytes)
    notes_hash: str | None = None
    if notes is not None:
        notes_path = _resolve_path(notes)
        if _is_path_traversal(notes_path, base):
            raise CLIError("path traversal is not allowed")
        notes_bytes = _safe_read(notes_path)
        notes_hash = HashEngine.hash_single_hex(notes_bytes)

    # Read source file exactly once into bytes for storage. For very large files
    # this is bounded by the 1 GB alpha ceiling enforced by _stream_hash.
    data = _safe_read(in_path, max_bytes=ALPHA_MAX_FILE_SIZE)

    # Build optional metadata dict; Archive.canonical_json() hashes it.
    metadata_dict: dict[str, Any] | None = None
    if metadata_hash is not None:
        metadata_dict = {"metadata_hash": metadata_hash}

    archive = Archive(str(base))
    manifest_hash = archive.add_document(
        data,
        title=title,
        media_type=media_type,
        language=language,
        source=source,
        source_uri=source_uri or source_identifier,
        acquisition_date=acquisition_date,
        license=license,
        parent_hash=parent_hash,
        notes_hash=notes_hash,
        metadata=metadata_dict,
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
        "network_id": manifest["network_id"],
        "schema_version": manifest["schema_version"],
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

    try:
        manifest = archive.get_manifest(manifest_hash)
    except Exception as exc:
        raise CLIError(f"manifest read failed: {exc}") from exc

    if manifest.get("network_id") != NETWORK_ID:
        raise CLIError("manifest network ID does not match this chain")
    if manifest.get("schema_version") != 1:
        raise CLIError("unsupported manifest schema version")

    # Recompute manifest hash from stored bytes to detect metadata tampering.
    mpath = archive.manifests_dir / manifest_hash
    stored_bytes = mpath.read_bytes()
    if HashEngine.hash_single_hex(stored_bytes) != manifest_hash:
        raise CLIError("manifest hash mismatch; manifest metadata has been tampered with")

    # Recompute content hash and length from stored bytes.
    try:
        content = archive.get_document(manifest["content_hash"])
    except Exception as exc:
        raise CLIError(f"content read failed: {exc}") from exc

    content_hash = HashEngine.hash_single_hex(content)
    if content_hash != manifest["content_hash"]:
        raise CLIError("content hash mismatch; document bytes have been modified")
    if len(content) != manifest["byte_length"]:
        raise CLIError("content length mismatch")

    click.echo(json.dumps({
        "manifest_hash": manifest_hash,
        "manifest_valid": True,
        "content_hash": manifest["content_hash"],
        "byte_length": len(content),
        "title": manifest["title"],
    }, indent=2))
