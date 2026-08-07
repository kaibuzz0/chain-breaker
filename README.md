# Chain-Breaker

A deterministic blockchain protocol for preserving documents, provenance, and historical curator attestations.

Current status: **v2.0.0-alpha — not production-ready.**

This repository is undergoing a consensus-correctness, archival-integrity, and
adversarial-testing phase. It does not yet implement P2P networking, wallets,
tokenomics, encrypted vaults, monetary settlement, or smart contracts.

## Implemented

* Protocol V2 consensus (frozen except for verified defects).
* Canonical binary block headers (149 bytes, type marker `0x02`).
* SHA-256d block hashing: `SHA256(SHA256(canonical_header_bytes))`.
* 256-bit integer proof-of-work target with retargeting at fixed boundaries.
* Deterministic registry governance (register, rotate, revoke) with Ed25519 signatures.
* Registry-root commitments: each block header commits to the registry state *before* the block.
* Historical Ed25519 attestations bound to the active curator set at a specific block height.
* Content-addressed archive with signed manifest schema.
* CLI V2 workflows via the `chainbreaker` entry point.
* Adversarial, fuzz, corruption, and replay test coverage.

## In development

* Durable flat-file storage with write-ahead journal and crash recovery.
* Snapshots and restart/replay optimization.
* Cross-language golden test vectors.
* Independent Rust verifier for header hashing and registry-root calculation.
* Consensus mutation testing.

## Not yet implemented

* Networking, peer protocol, gossip, sync.
* Reorganization engine and fork-choice rules.
* Monetary settlement, tokenomics, or smart-contract execution.
* Long-range-attack protection beyond genesis and accumulated chain work.

## Protocol overview

See `docs/PROTOCOL.md` for the complete V2 specification:

* canonical binary header encoding
* SHA-256d block hashing and proof-of-work target interpretation
* difficulty retargeting and chain-work accumulation
* genesis constants
* Ed25519 witness pre-image and validation
* curator-registry state, activation, revocation, and rotation
* registry-root commitment semantics

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # .venv\\Scripts\\activate on Windows
pip install -e ".[dev]"

# Show the canonical genesis block
chainbreaker genesis

# Generate a curator keypair
chainbreaker v2 curator generate --output-sk alice.sk.hex --output-pk alice.pk.hex

# Add a document to the archive
chainbreaker v2 archive add --data-dir ./archive --file README.md --title "README" --media-type text/plain

# Verify a stored manifest
chainbreaker v2 archive verify --data-dir ./archive --manifest-hash <hash>

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
ruff check chainbreaker tests
mypy chainbreaker
python -m build
pip-audit -r requirements.txt
bandit -r chainbreaker
```

## Known unresolved risks

* **No network layer.** All consensus rules are validated locally; a future P2P layer must replay the same deterministic rules.
* **No checkpointing or long-range-attack protection.** Genesis and chain-work are the only trust anchors.
* **No durable storage implementation.** The V2 CLI stores data as local JSON/flat files; crash recovery and atomic commits are in Phase 7A.
* **Cross-language manifest standard is planned.** Canonical JSON is stable but a binary manifest standard and independent verifier are in Phase 7B/7C.

## License

MIT

## Security properties

- **Private keys** are written atomically with 0o600 permissions on POSIX and are never printed, logged, or serialized.
- **Atomic writes** use same-directory temp files and `os.replace`; failures leave the original file unchanged.
- **Path traversal** (`..`) and symlink writes are rejected for inputs and security-sensitive outputs.
- **Archive size**: files larger than 1 GB are rejected (alpha hard ceiling, no override).
- **No network access**: all v2 commands are local-only and never make HTTP or shell requests.
- **Strict UTF-8**: all manifest and transaction JSON is read and written as UTF-8 with deterministic key ordering.
