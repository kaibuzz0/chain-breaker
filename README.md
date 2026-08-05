# Chain-Breaker

A minimal, consensus-first ledger for preserving canonical, signed scripture and archive manifests.

This repository is currently an **alpha prototype** undergoing a consensus-correctness, archival-integrity, and adversarial-testing phase. It is **not** production-ready and does **not** yet implement P2P networking, wallets, tokenomics, or encrypted vaults.

## What it proves today

* A single canonical `chainbreaker/` package.
* 256-bit integer proof-of-work target, not a bit-count proxy.
* Difficulty retargeting only at fixed boundaries using accumulated work.
* Double-SHA-256 block hashing (not triple) with a hard-coded canonical genesis.
* Ed25519 curator attestations bound to an activation-height registry.
* Separation of submission freshness from historical signature validity.
* Enforced transaction schemas and witness validation inside consensus.
* Content-addressed archive with signed manifest schema.

## Protocol overview

See `docs/PROTOCOL.md` for the complete specification of:

* transaction encoding
* block hashing
* target calculation and retargeting
* chain-work accumulation
* genesis constants
* witness pre-image and validation
* curator-registry state, activation, revocation, and rotation

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # .venv\\Scripts\\activate on Windows
pip install -e ".[dev]"

# Show the canonical genesis block
chainbreaker genesis

# Generate a curator keypair
chainbreaker curator generate --curator-id alice

# Add a document to the archive (Protocol v2)
chainbreaker v2 archive add --data-dir ./archive --file README.md --title "README" --media-type text/plain

# Verify a stored manifest
chainbreaker v2 archive verify --data-dir ./archive --manifest-hash <hash>

# Generate a curator keypair (Protocol v2)
chainbreaker v2 curator generate --output-sk alice.sk.hex --output-pk alice.pk.hex

# Register a curator via governance
chainbreaker v2 governance register --ledger ledger.json --curator-id alice --public-key <hex> --activation-height 2 --governance-key gov.sk.hex --key-index 0 --output reg.json

# Mine and add a block
chainbreaker v2 block mine --ledger ledger.json --transactions reg.json --output block.json
chainbreaker v2 block add --ledger ledger.json --block block.json

# Attest a manifest at a historical height
chainbreaker v2 attest create --ledger ledger.json --manifest <hash-or-json> --curator-id alice --block-height 2 --private-key alice.sk.hex --output att.json
chainbreaker v2 attest verify --ledger ledger.json --attestation att.json --manifest <hash-or-json> --block-height 2
```

## Verification

```bash
pytest -v
pytest --cov=chainbreaker --cov-report=term-missing
ruff check chainbreaker tests
mypy chainbreaker
python -m build
pip-audit -r requirements.txt
bandit -r chainbreaker
```

## Known unresolved risks

* **CLI tests are smoke tests only.** The `mine` command currently uses a placeholder signer identity (`alpha`) and does not yet enforce registry governance on chain.
* **Registry transactions are parsed but not committed into the ledger state machine.** They can be injected into blocks, but the ledger does not automatically derive a deterministic registry from chain history.
* **No network layer.** All consensus rules are validated locally; a future P2P layer must replay the same deterministic rules.
* **No checkpointing or long-range-attack protection.** Genesis and chain-work are the only trust anchors.
* **Canonical JSON is Python-only.** A cross-language binary manifest standard is planned for a later phase.

## License

MIT


## Security properties

- **Private keys** are written atomically with 0o600 permissions on POSIX and
  are never printed, logged, or serialized.
- **Atomic writes** use same-directory temp files and `os.replace`; failures
  leave the original file unchanged.
- **Path traversal** (`..`) and symlink writes are rejected for inputs and
  security-sensitive outputs.
- **Archive size**: files larger than 1 GB are rejected (alpha hard ceiling,
  no override).
- **No network access**: all v2 commands are local-only and never make HTTP or
  shell requests.
- **Strict UTF-8**: all manifest and transaction JSON is read and written as
  UTF-8 with deterministic key ordering.
