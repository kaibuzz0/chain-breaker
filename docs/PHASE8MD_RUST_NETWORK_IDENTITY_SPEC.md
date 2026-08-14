# Phase 8M-D: Independent Python/Rust Network Identity Verification Expansion

## Goal

Remove the Rust verifier's hardcoded assumption that only the alpha network
identity (`chainbreaker-scripture-v2`) exists. Make the Rust verifier consume
network identity/genesis parameters from frozen vectors and independently derive
the same registry serialization, registry root, genesis header bytes, and genesis
hash that Python derives.

## Scope

- `rust-verifier/src/network_identity.rs` — new module for network identity
  parsing, registry state serialization, registry root computation, and genesis
  header mining.
- `rust-verifier/src/lib.rs` — expose network identity helpers; remove hardcoded
  network ID from `build_governance_message`.
- `rust-verifier/src/main.rs` — add `check_network_identities` and pass
  vector-supplied `network_id` to governance message checks.
- `test-vectors/network-identities.json` — frozen positive and negative vectors.
- `test-vectors/network-identities-test-genesis.bin` / `.hash` — sidecars for
  the test identity.
- `test-vectors/generate_network_identity_vectors.py` — deterministic Python
  generator for the vectors.
- `test-vectors/validate_vectors.py` — validate vectors against Python
  derivation.
- `tests/test_phase8md_network_identity_verification.py` — regression tests.

## Out of scope

- README updates (deferred to 8M-E truth freeze).
- Changes to the Python consensus model beyond exposing derivation helpers.
- Production ceremony tooling; vector keys are clearly labeled as test-only.

## Cross-implementation contract

Given the same inputs:

```text
network_id
governance_keys (sorted)
governance_threshold
genesis_timestamp
```

Both Python and Rust must derive:

```text
identical registry state bytes
identical registry root
identical genesis header bytes
identical genesis hash
```

Changing any input must produce a different, but again matching, result in both
implementations.

## Negative vectors

- `wrong_network_id` — different `network_id` with same keys/threshold.
- `wrong_governance_key` — one key changed with same `network_id`/threshold.
- `wrong_threshold` — threshold changed with same `network_id`/keys.
- `wrong_genesis_root` — a tampered registry root does not match the
  independently derived header.

## Alpha vector immutability

The alpha/legacy identity vector is frozen and references the existing
`chainbreaker-scripture-v2` genesis constants. No alpha genesis, hash, or registry
file is regenerated.
