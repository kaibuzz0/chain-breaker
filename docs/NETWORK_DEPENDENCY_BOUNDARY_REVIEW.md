# Network Dependency Boundary Review

## Scope

Review of `chainbreaker/network/` after Phase 8B implementation.

## Question

Does the network package depend on consensus, storage, state, or ledger code?

## Method

Static inspection of imports in:

- `chainbreaker/network/__init__.py`
- `chainbreaker/network/constants.py`
- `chainbreaker/network/errors.py`
- `chainbreaker/network/envelope.py`
- `chainbreaker/network/codec.py`
- `chainbreaker/network/messages.py`
- `chainbreaker/network/validation.py`

## Findings

Only non-consensus dependencies are used:

- `chainbreaker.crypto.HashEngine` — for payload SHA-256 hashing. This module
  contains generic SHA-256 helpers and Ed25519 wrappers; it is not
  consensus-specific in use, though it is also used by consensus.
- Standard library: `struct`, `dataclasses`, `json`, `re`, `typing`.

No imports from:

- `chainbreaker.block`
- `chainbreaker.chain`
- `chainbreaker.consensus`
- `chainbreaker.storage`
- `chainbreaker.registry_state`
- `chainbreaker.archive`
- `chainbreaker.governance`
- `chainbreaker.witness`

## Reverse dependency check

No consensus file imports from `chainbreaker.network`. The consensus core
remains network-free.

## Conclusion

The Phase 8B network parser is a pure transport/serialization layer. The
network-consensus boundary defined in ADR 010 is preserved.
