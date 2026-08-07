# Chain-Breaker Independent Rust Verifier

A minimal, dependency-light Rust crate that independently verifies the
consensus-critical computations of Chain-Breaker Protocol v2.

## Scope

- Header v2 canonical serialization (149 bytes).
- Double SHA-256 block hashing.
- Proof-of-work target comparison.
- Genesis header validation against frozen constants.
- Registry-root calculation from canonical registry-state bytes.

This crate does **not** implement networking, storage, CLI, or consensus
policy beyond pure arithmetic/serialization checks. It is intended as a
cross-language correctness oracle for the Python implementation.

## Build

```bash
cargo build --release
cargo test
```

## Usage

```bash
cargo run --bin verify-vectors -- ../test-vectors
```
