# Chain-Breaker Developer Guide

This guide is for developers who want to understand, extend, or audit the Chain-Breaker codebase.

## Repository layout

```text
chainbreaker/
  codec.py          — canonical serialization
  block.py          — block and header data structures
  consensus.py      — validation rules
  registry_state.py — curator registry reducer
  governance.py     — curator action helpers
  witness.py        — attestation creation and verification
  archive.py        — archive persistence
  cli_v2.py         — operator CLI
  crypto.py         — cryptographic helpers
tests/              — pytest suite
docs/               — design and operational docs
```

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e .[dev]
```

## Running tests

```bash
pytest -v
```

For CI-parity on Windows, use the full workflow:

```bash
python -m pytest -v
python -m ruff check chainbreaker tests
python -m mypy chainbreaker
python -m bandit -r chainbreaker
pip-audit
```

## Layer rules

Before changing code, read `docs/ARCHITECTURE.md`. The most important rule:

> Layers 1 and 2 (consensus and registry governance) are frozen. Changes require an ADR and a protocol version bump.

Dependency direction is strictly downward:

```text
CLI -> Archive -> Registry -> Consensus
```

## Adding a new CLI command

1. Add the command handler in `chainbreaker/cli_v2.py`.
2. Add end-to-end tests in `tests/test_cli_v2.py`.
3. Update `docs/CLI_V2_GUIDE.md`.
4. If the command changes the frozen API, update `docs/adr/003-cli-api-freeze.md`.

## Adding a new consensus feature

1. Write an ADR in `docs/adr/`.
2. Implement the change, ideally in a new module (e.g. `block_v3.py`).
3. Add deterministic test vectors to `tests/`.
4. Update `docs/ARCHITECTURE.md` if layer boundaries change.
5. Bump the protocol version in the relevant header field.

## Writing tests

- Prefer invariants over snapshot assertions.
- Use `tmp_path` for filesystem tests; never touch `~/.hermes` or real home directories.
- Adversarial tests should mutate one canonical field at a time and assert rejection.
- Deterministic tests must pass on Python 3.10, 3.11, and 3.12.

## Security code review checklist

When modifying CLI or archive code, verify:

- [ ] All file paths are resolved and checked for symlink traversal before access.
- [ ] Path traversal (`..`) is rejected.
- [ ] Overwrites require explicit `--force`.
- [ ] Atomic writes are used for all state files.
- [ ] Private-key material is never logged.
- [ ] Free-form input is UTF-8 validated.

## Useful debugging commands

Dump the canonical header bytes of a block:

```python
from chainbreaker.codec import encode_header
from chainbreaker.archive import load_block
block = load_block("./chain/block_0001.bin")
print(encode_header(block.header).hex())
```

Replay the registry reducer step by step:

```python
from chainbreaker.registry_state import replay_registry
from chainbreaker.archive import load_chain
chain = load_chain("./chain")
for height, root in enumerate(replay_registry(chain)):
    print(height, root.hex())
```
