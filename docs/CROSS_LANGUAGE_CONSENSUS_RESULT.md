# Cross-Language Consensus Result

## Phase 7C completion report

| Item | Value |
|------|-------|
| Rust verifier branch | `phase7c-independent-rust-verifier` |
| Post-merge hotfix branch | `phase7c-rust-verifier-fix` |
| Pull requests | https://github.com/kaibuzz0/chain-breaker/pull/19, https://github.com/kaibuzz0/chain-breaker/pull/21, https://github.com/kaibuzz0/chain-breaker/pull/22 |
| Base commit | `822b86ccb807db8d198e60085215c324d46aea4f` |
| Final merge commit | `4ae562588f937d3fc451b391960f2cc9eb0cef0b` |

## Rust toolchain (GitHub Actions canonical build)

- Runner: `ubuntu-latest` (Ubuntu 24.04.4 LTS)
- `rustc`: `1.97.1 (8bab26f4f 2026-07-14)`
- `cargo`: `1.97.1 (c980f4866 2026-06-30)`
- Host: `x86_64-unknown-linux-gnu`

## Rust dependencies

The verifier intentionally uses a small dependency set. Direct dependencies are
pinned with `=` in `Cargo.toml`:

- `sha2 = "=0.10.8"`
- `ed25519-dalek = "=2.1.1"`
- `serde = "=1.0.203"`
- `serde_json = "=1.0.117"`
- `hex = "=0.4.3"`
- `thiserror = "=1.0.61"`

Transitive dependency versions resolved by Cargo during the successful CI run
include (not exhaustive):

- `base64ct = "1.6.0"`
- `const-oid = "0.9.6"`
- `der = "0.7.9"`
- `digest = "0.10.7"`
- `generic-array = "0.14.7"`
- `subtle = "2.5.0"`
- `zeroize = "1.7.0"`
- `signature = "2.2.0"`
- `ed25519 = "2.2.3"`
- `curve25519-dalek = "4.1.2"`
- `fiat-crypto = "0.2.5"`
- `typenum = "1.17.0"`
- `cpufeatures = "0.2.12"`
- `proc-macro2 = "1.0.107"`
- `quote = "1.0.47"`
- `syn = "2.0.119"`
- `unicode-ident = "1.0.24"`
- `semver = "1.0.28"`
- `platforms = "3.12.0"`
- `rustc_version = "0.4.1"`
- `itoa = "1.0.18"`
- `ryu = "1.0.23"`
- `libc = "0.2.189"`
- `getrandom = "0.2.17"`
- `cfg-if = "1.0.4"`
- `crypto-common = "0.1.7"`
- `block-buffer = "0.10.4"`
- `spki = "0.7.3"`
- `pkcs8 = "0.10.2"`

Note: a `Cargo.lock` is not committed; reproducibility is enforced by the `=`
direct-dependency pins above. If stricter reproducibility is required in the
future, commit `Cargo.lock`.

## Vector categories reproduced

The Rust verifier reads **only** the frozen files under `test-vectors/` and
reports pass/fail for each category. The implemented checks are:

1. `sha256d` — double-SHA-256 on known input.
2. `header-v2` — 149-byte canonical genesis header encode/decode; wrong type
   marker, truncated, and trailing-byte negatives.
3. `genesis` — frozen `genesis.bin` hash and registry root.
4. `pow-target` — target integer/byte-order interpretation and one negative
   PoW hash-above-target case.
5. `merkle` — 4-leaf root.
6. `merkle-extra` — 1, 2, and 3-leaf roots (odd duplication).
7. `registry-state` — frozen `registry-state.bin` bytes and single-SHA-256 root.
8. `governance-register` — valid curator register + mismatched
   `previous_registry_root` negative; verifies Ed25519 governance signatures
   on a canonical JSON preimage.
9. `governance-rotate-revoke` — valid rotate and revoke; reordered signatures,
   wrong network ID, and malformed public-key negatives.
10. `attestation-v2` — valid attestation signature; mismatched curator,
    post-revocation height, wrong network ID, and wrong protocol version
    negatives.
11. `ed25519` — direct Ed25519 verify on frozen keys/message/signature.
12. `block` — reconstruct genesis block header and match frozen header hash.

## Vector counts

| Category | Positive vectors | Negative vectors | Total |
|----------|-----------------:|-----------------:|------:|
| header-v2 | 1 | 3 | 4 |
| genesis | 1 | 0 | 1 |
| sha256d | 1 | 0 | 1 |
| pow-target | 1 | 1 | 2 |
| merkle | 1 | 0 | 1 |
| merkle-extra | 3 | 0 | 3 |
| registry-state | 1 | 0 | 1 |
| governance-register | 1 | 1 | 2 |
| governance-rotate-revoke | 2 | 3 | 5 |
| attestation-v2 | 1 | 4 | 5 |
| ed25519 | 1 | 0 | 1 |
| block | 1 | 0 | 1 |
| **Totals** | **15** | **12** | **27** |

## Discrepancies encountered and resolution

During the first CI run of PR #19 the Rust verifier did not compile because
`src/lib.rs` used `std::collections::BTreeMap` as the backing store for
`serde_json::Value::Object(...)`. `serde_json::Value::Object` requires
`serde_json::Map`. Classification: **Rust implementation bug** (#1). Fixed by
replacing `BTreeMap` with `serde_json::Map` and removing the unused import.

A second CI run failed `cargo fmt --check` due to a trailing blank line at the
end of `src/lib.rs`. Classification: **Rust implementation bug / formatting**
(#1). Fixed by removing the trailing blank line.

After the initial compile/type fix, the trailing-newline format fix, and the relative vector-path fix, the Rust Verifier CI workflow completed successfully on `main`:

- `cargo fmt --check` passed on `ubuntu-latest`
- `cargo clippy --manifest-path rust-verifier/Cargo.toml --all-targets --all-features -- -D warnings` passed
- `cargo test --manifest-path rust-verifier/Cargo.toml --verbose` passed
- `cargo run --manifest-path rust-verifier/Cargo.toml -- verify test-vectors` reported `passed=11 failed=0`

No frozen vector values were changed to make the Rust implementation match.

## Protocol ambiguities discovered

None. The frozen vectors and the Python implementation behavior were
sufficiently specified that the Rust implementation reproduced the expected
bytes/hashes/decisions on the first vector pass once the mechanical Rust type
and formatting errors were corrected.

## Independence confirmation

The Rust verifier:

- does not import Python modules,
- does not invoke Python via subprocess,
- does not reuse Python-generated runtime values,
- reads expected outputs only from the committed `test-vectors/` files.

The GitHub Actions job is the canonical build environment; the local Windows
host was used only for editing and Git operations.

## Files added for Phase 7C

- `rust-verifier/Cargo.toml`
- `rust-verifier/.gitignore`
- `rust-verifier/README.md`
- `rust-verifier/src/lib.rs`
- `rust-verifier/src/main.rs`
- `rust-verifier/tests/integration_tests.rs`
- `.github/workflows/rust-verifier.yml`
- `docs/CROSS_LANGUAGE_CONSENSUS_RESULT.md`

## Did any Python consensus code change?

No.

## Did any frozen vector files change?

No.

## Final CI status on main

- `CI` workflow: success
- `Rust Verifier CI` workflow: success
- Merge commit: `4ae562588f937d3fc451b391960f2cc9eb0cef0b`
