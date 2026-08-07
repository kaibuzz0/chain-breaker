# Chain-Breaker V2 Independent Rust Verifier

This crate re-implements the consensus-critical primitives of Chain-Breaker
Protocol V2 in Rust. It reads only the frozen `test-vectors/` files from the
parent repository and verifies that the Rust implementation reproduces the
expected bytes, hashes, and decisions exactly.

## Independence rules

- No Python imports.
- No subprocess calls to Python.
- No runtime use of Python-generated values.
- Expected outputs come only from frozen vector files.

## Run

```bash
cargo run --manifest-path rust-verifier/Cargo.toml -- verify test-vectors
```

## Test

```bash
cargo test --manifest-path rust-verifier/Cargo.toml
```
