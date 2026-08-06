# API Freeze — v2.0.0-alpha

## CLI entry point

- Command: `hon`
- Top-level subcommands frozen at alpha:
  - `chain verify`
  - `curator generate`
  - `curator register`
  - `curator rotate`
  - `curator revoke`
  - `block mine`
  - `block add`
  - `archive add`
  - `archive verify`
  - `attest create`
  - `attest verify`

## Library API

Public functions in the following modules are considered stable:

- `chainbreaker.codec` — canonical encode/decode.
- `chainbreaker.consensus` — block validation.
- `chainbreaker.registry_state` — registry reducer.
- `chainbreaker.witness` — attestation verification.

## Stability rule

Backward-incompatible changes to frozen CLI commands or library functions require a minor version bump and a migration note in the next release package.
