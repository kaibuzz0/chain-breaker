# Phase 8M-A Consensus Validation Hardening Report

**Branch:** `phase8ma-consensus-validation-hardening`  
**Date:** 2026-08-14  
**Scope:** Confirmed V2 transaction-validation gap only. 8M-B/E not started.

## 1. Executive Summary

Phase 8M-A closes the confirmed consensus-critical gap where V2 blocks and
transactions could bypass baseline schema validation through the optional
`transaction_validator` callback in `Ledger.__init__` / `BlockV2.verify()` /
`Ledger.add_block_v2()`.  The fix makes generic V2 transaction schema validation
mandatory on every V2 acceptance path while keeping governance, archive, and
custom validators layered *on top* of the baseline.

## 2. Acceptance-Path Map

The read-only map was committed as
`docs/PHASE8MA_ACCEPTANCE_PATH_MAP.md`.  Key findings:

| Path | Generic schema | Governance | Archive/Scripture | Witness | Optional callback | Malformed tx can mutate state? |
|---|---|---|---|---|---|---|
| `BlockV2.verify()` | **Optional** via callback | callback-only | callback-only | callback-only | Yes | Yes (if callback omitted) |
| `Ledger.add_block_v2()` | **Optional** via callback | callback-only | callback-only | callback-only | Yes | Yes (if callback omitted) |
| `Ledger.mine_block_v2()` | **Optional** via `validate_transaction` (legacy, wrong schema) | none | none | none | N/A | Yes (could mine malformed tx) |
| chain replay / `validate_chain()` | **Optional** (inherits callback) | callback-only | callback-only | callback-only | Yes | Yes |
| CLI block add/mine | same as Ledger methods | same | same | same | same | same |
| sync ingestion (`SyncEngine.handle_block()`) | converges on `add_block_v2()` | converges | converges | converges | Yes | Yes (pre-fix) |
| relay ingestion (`RelayEngine.handle_block()`) | converges on `add_block_v2()` | converges | converges | converges | Yes | Yes (pre-fix) |
| storage restore/replay | loads bytes; validation depends on caller | caller-dependent | caller-dependent | caller-dependent | Yes | Yes if caller skips validation |

Root cause: `Ledger.__init__(transaction_validator=None)` defaulted to no
validator; `BlockV2.verify()` only validated transactions when a callback was
supplied; `Ledger.add_block_v2()` passed `self.transaction_validator` directly;
sync/relay called `add_block_v2()` with the ledger's (possibly None) validator.

## 3. Architecture Chosen

The smallest architecture that satisfies the requirements:

1. Introduce `chainbreaker.codec.validate_v2_transaction(tx)` — a schema-only
   validator that understands the **actual** V2 transaction envelopes used by
   the consensus path (`genesis`, `governance`, `scripture`), including both
   the canonical wire form with `version`/`type`/`body`/`witnesses` and the
   internal governance form `type`/`body`.
2. Call `validate_v2_transaction()` unconditionally inside:
   - `BlockV2.verify()` — mandatory before any optional callback runs.
   - `Ledger.mine_block_v2()` — mandatory before mining.
3. Leave the optional `transaction_validator` callback intact as an
   **additional** application-specific layer; it can strengthen checks but can
   no longer disable baseline validation.
4. Leave `validate_transaction()` (legacy v1 codec validator) unchanged to avoid
   breaking v1/witness paths.
5. Add a test helper `tests._adversarial_block_helpers.mine_adversarial_block`
   so existing adversarial tests can still craft malformed blocks to verify that
   network layers reject them, now that the legitimate miner refuses to do so.

## 4. Files Changed

Core changes:
- `chainbreaker/codec.py` — added `validate_v2_transaction()`.
- `chainbreaker/block.py` — `BlockV2.verify()` now calls `validate_v2_transaction()` unconditionally.
- `chainbreaker/chain.py` — `Ledger.mine_block_v2()` now calls `validate_v2_transaction()` unconditionally.

Test changes:
- `tests/test_phase8ma_consensus_validation_hardening.py` — 10 regression tests covering every acceptance path.
- `tests/test_adversarial_corruption.py` — updated `test_invalid_public_key_in_governance_rejected` to use a valid-schema/invalid-authorization input so governance validation is still exercised.
- `tests/network/adversarial/conftest.py` — added `mine_adversarial` helper and imported shared helper.
- `tests/network/adversarial/test_combined_attacks.py`, `test_relay_attacks.py`, `test_sync_attacks.py` — use adversarial helper.
- `tests/network/relay/test_relay_adversarial.py` — use adversarial helper.
- `tests/_adversarial_block_helpers.py` — new shared helper for mining invalid blocks in adversarial tests.

Documentation:
- `docs/PHASE8MA_ACCEPTANCE_PATH_MAP.md` — read-only acceptance-path map.
- This report: `docs/PHASE8MA_CONSENSUS_VALIDATION_HARDENING_REPORT.md`.

## 5. Tests Added

`tests/test_phase8ma_consensus_validation_hardening.py`:

1. `test_block_v2_verify_rejects_malformed_transaction`
2. `test_add_block_v2_rejects_malformed_transaction`
3. `test_validate_chain_rejects_malformed_transaction`
4. `test_sync_rejects_malformed_transaction`
5. `test_relay_rejects_malformed_transaction`
6. `test_custom_validator_cannot_bypass_baseline_validation`
7. `test_governance_authorization_still_rejected_with_valid_schema`
8. `test_valid_governance_transaction_accepted`
9. `test_mine_block_v2_rejects_malformed_transaction`
10. `test_validate_v2_transaction_accepts_canonical_wire_form`

All 10 pass.

## 6. Previously Accepted Malformed Blocks

Under the old code, any V2 block containing a transaction that failed the
legacy `validate_transaction()` schema (e.g., `type: "governance"` transactions,
`{"id": "foo"}` junk, or a transaction with `type` not in
`{genesis, scripture, registry}`) would be accepted if no custom validator
was supplied.  After this change, those malformed transactions are rejected at:

- mining time (`mine_block_v2()`), and
- verification time (`BlockV2.verify()` / `add_block_v2()`).

This is intentional and is the primary security objective of 8M-A.

## 7. Compatibility Impact

- **Existing valid V2 transactions remain accepted** — verified by
  `test_valid_governance_transaction_accepted` and the full governance/registry
  test suite.
- **Genesis block unchanged** — genesis uses `type: "genesis"`, which is
  supported by `validate_v2_transaction()`.
- **CLI and network paths unchanged** in protocol semantics; they now converge
  on the authoritative validation path instead of the optional callback.
- **Legacy v1 path (`mine_block`) unchanged** — still uses `validate_transaction()`.

## 8. Frozen-Vector Impact

- No frozen vector or genesis artifact was modified.
- `tests/test_genesis_v2.py` (13 tests) and `tests/test_codec.py` (9 tests)
  pass unchanged, confirming frozen header/transaction vectors are intact.
- No previously accepted valid vector is now rejected.

## 9. Consensus Behavior Impact

- `BlockV2.verify()` now always performs baseline schema validation.
- `Ledger.mine_block_v2()` now always performs baseline schema validation.
- Optional `transaction_validator` callbacks are additive only.
- Governance validation in `Ledger.add_block_v2()` still runs after schema
  validation and still rejects unauthorized/mutated governance transactions.
- Sync and relay paths reject malformed blocks through the same authoritative
  `add_block_v2()` gate.

## 10. Verification Gates

| Gate | Status |
|---|---|
| Core consensus tests (block/chain/codec/adversarial) | **PASS** (65 passed) |
| Network tests | **PASS** (network adversarial 23 passed; full network suite 314+ passed) |
| Storage/reorg tests | **PASS** (subset 655 passed) |
| New 8M-A regression tests | **PASS** (10 passed) |
| Ruff | **PASS** |
| mypy | **PASS** |
| Build | **PASS** (wheel + sdist built) |
| Bandit | **PASS** |
| pip-audit | **PASS** (no known vulnerabilities) |
| Python genesis/codec frozen vectors | **PASS** |
| Rust verifier | **N/A locally** — Rust toolchain not installed on this Windows host; CI will run it. |
| Targeted consensus mutation smoke | **N/A locally** — `scripts/run_consensus_mutations.py` is a full campaign that copies the tree and runs all harnesses per mutation; it targets ~10 min per mutation and is intended for CI. |

## 11. Unresolved Risks

1. **Storage restore path**: `StorageBackend.read_block()` returns bytes/blocks;
  callers such as sync/relay already re-validate via `add_block_v2()`, but a
  future consumer that loads directly from storage without re-validation could
  re-introduce the gap.  8M-B (archive integrity) and 8M-C (genesis ceremony)
  will address related concerns.
2. **Legacy `validate_transaction()` drift**: the v1 validator still rejects
  governance transactions. This is acceptable because V2 paths now use
  `validate_v2_transaction()`, but it means the legacy function is not
  authoritative for V2. Documenting this boundary is part of the truth freeze in
  8M-E.
3. **Rust verifier toolchain unavailable locally**; CI must confirm the Rust
  verifier still agrees with Python on genesis/frozen vectors.

## 12. Next Step

Phase 8M-A is implementation-complete. The branch is ready for push and CI.
Phase 8M-B (Archive Integrity Hardening) can begin only after this branch is
CI-green and merged.
