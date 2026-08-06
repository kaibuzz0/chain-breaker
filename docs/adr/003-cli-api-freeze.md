# ADR 003 — CLI and Library API Freeze

## Status

Accepted — frozen at v2.0.0-alpha.

## Context

Operators and downstream tools need a stable interface to the engine. Without a frozen API, scripts, tests, and integrations break every time the CLI changes.

## Decision

The following CLI commands and library functions are frozen for alpha:

### CLI commands

- `hon chain verify`
- `hon curator generate`
- `hon curator register`
- `hon curator rotate`
- `hon curator revoke`
- `hon block mine`
- `hon block add`
- `hon archive add`
- `hon archive verify`
- `hon attest create`
- `hon attest verify`

### Library API

- `chainbreaker.codec.encode_*` and `decode_*`
- `chainbreaker.consensus.validate_block`
- `chainbreaker.registry_state.apply_action`
- `chainbreaker.witness.create_attestation` and `verify_attestation`

## Rationale

A stable CLI makes the project usable without Python knowledge. A stable library API makes integration tests and downstream tooling reliable.

## Alternatives considered

| Approach | Rejected because |
|----------|------------------|
| Keep CLI experimental | Operators cannot build scripts or runbooks. |
| Freeze the whole package | Prevents necessary internal refactoring for networking/storage. |
| Use a separate `honctl` binary | Adds packaging complexity before networking exists. |

## Invariants that must never change

1. Command names above remain available and perform the same semantic operation.
2. Exit codes are stable: `0`, `1`, `2`, `3`.
3. Library function signatures for the listed functions remain backward-compatible.
4. Path-traversal and symlink rejection remain mandatory for all file operations.

## Extension points

- New commands can be added (e.g. `hon node`, `hon sync`).
- New flags can be added if they default to current behavior.
- Internal helper functions can change; public API functions cannot without a minor version bump.

## Compatibility implications

- Breaking the frozen CLI or library API requires a minor version bump and a migration note.
