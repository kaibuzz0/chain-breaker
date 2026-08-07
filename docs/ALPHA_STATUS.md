# Chain-Breaker Alpha Status

This document is a concise status page for the **v2.0.0-alpha** milestone. It tells contributors what is stable, what is frozen, what remains experimental, and what is intentionally unsupported.

## What is production-stable

- **Consensus engine** — Protocol v2 block validation, canonical serialization, and proof-of-work.
- **Registry governance** — Curator register, rotate, revoke reducer with registry-root commitments.
- **Historical attestations** — Witness creation and verification against the active curator set.
- **CLI v2** — Operator commands for chain, curator, block, archive, and attestation workflows.
- **Testing** — 756+ tests with deterministic, replay, corruption, and fuzz coverage.
- **Security hardening** — Path traversal rejection, symlink rejection, atomic writes, UTF-8 validation.
- **Packaging** — Wheel builds and entry-point installation.
- **Cross-platform CI** — Python 3.10, 3.11, 3.12 passing on Linux via GitHub Actions.

## What is frozen

Frozen items require an ADR and a protocol/API version bump to change:

1. Header v2 field order and canonical encoding.
2. SHA-256d (`SHA256(SHA256(...))`) block hashing.
3. Registry governance reducer transitions.
4. CLI command names and argument semantics listed in `docs/adr/003-cli-api-freeze.md`.
5. Library API surface listed in `docs/adr/003-cli-api-freeze.md`.

## What remains experimental

- Storage backend interface (the current flat-file implementation is the only backend).
- Archive compaction and snapshot tooling.
- CLI help text, output formatting, and progress indicators.
- Internal benchmark harness iteration counts and suite definitions.

## What is intentionally unsupported

- Networking and peer-to-peer communication.
- Distributed consensus or byzantine-fault tolerance.
- Mempool and transaction propagation.
- Chain reorganization and fork-choice beyond longest valid chain.
- Multi-node replication or clustering.
- Production monitoring, metrics, or alerting.
- Mobile or browser clients.

## Roadmap to Phase 7

| Phase | Focus |
|-------|-------|
| 7 | Storage backends, snapshot format, pruning, replay optimization, database abstraction |
| 8 | Peer protocol, handshake, inventory messages, block/transaction propagation, sync |
| 9 | Reorg engine, checkpoints, fork-choice testing, latency simulation |
| 10 | Independent code review, cryptographic review, serialization audit, documentation review |

## Reference documents

- `docs/ARCHITECTURE.md` — master system map
- `docs/adr/001-protocol-v2.md` — protocol freeze
- `docs/adr/002-consensus-freeze.md` — consensus freeze
- `docs/adr/003-cli-api-freeze.md` — API freeze
- `docs/THREAT_MODEL.md` — security assumptions and gaps
- `docs/OPERATOR_GUIDE.md` — operator usage
- `docs/DEVELOPER_GUIDE.md` — contributor guide
- `docs/EXTERNAL_AUDIT_CHECKLIST.md` — review checklist
- `docs/releases/v2.0.0-alpha/` — release artifact snapshot
- `benchmarks/results/alpha-f2e7bfd.md` — performance baseline
