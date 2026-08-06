# Release Notes — Chain-Breaker v2.0.0-alpha

## Milestones delivered

- **Protocol v2**: canonical serialization, header v2, genesis v2, deterministic PoW.
- **Consensus**: registry-governance reducer, registry-root commitments, historical attestation validation, replay/corruption/fork fuzzing.
- **CLI v2**: end-to-end Protocol v2 workflows via `hon` entry point.
- **Packaging**: wheel builds and entry-point installation verified.
- **Cross-platform CI**: Python 3.10, 3.11, 3.12 on Ubuntu via GitHub Actions.

## Notable fixes since last milestone

- Symlink rejection order hardened for Linux CI (two filesystem-behavior fixes).
- CLI security review: path traversal rejection, atomic writes, overwrite/symlink controls.

## Entry points

- `hon --help` — top-level CLI.
- `hon chain`, `hon curator`, `hon block`, `hon archive`, `hon attest`, `hon verify` — v2 workflows.

## Known call-outs

See `KNOWN_LIMITATIONS.md` for what is deliberately not included.
