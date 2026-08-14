# Phase 8M-A Acceptance-Path Map

## Scope

This document maps every V2 block admission path in the current codebase and documents what validation runs on each path. It is read-only analysis produced before any code changes.

**Branch:** `phase8ma-consensus-validation-hardening`
**Base commit:** `2c5a24a7b7addc38cc690c60a04d4c0827c34639`
**Date:** 2026-08-13

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | validation runs unconditionally |
| ⚠️ | validation runs conditionally or partially |
| ❌ | validation does not run |
| N/A | not applicable for this path |
| callback | depends on optional `transaction_validator` argument |

---

## 1. `BlockV2.verify()` — `chainbreaker/block.py:347`

**Called by:**
- `Ledger.add_block_v2()`
- `Ledger.validate_chain()`
- tests

**Validation performed:**

| Check | Status | Notes |
|-------|--------|-------|
| Header version == 2 | ✅ | hardcoded `PROTOCOL_VERSION` |
| Genesis allowed | ✅ | if `allow_genesis=True` and `is_genesis()` |
| Target bounds | ✅ | `MIN_TARGET <= target <= MAX_TARGET` |
| Merkle root recomputed | ✅ | compares `self.merkle_root()` to header |
| Proof of work | ✅ | `satisfies_pow(self.hash, target)` |
| Expected target | ⚠️ | only if caller passes `expected_target` |
| Timestamp > 0 | ✅ | unconditional |
| Future-timestamp bound | ⚠️ | only if caller passes `reference_time` |
| Median-past rule | ⚠️ | only if caller passes `median_past` |
| **Generic transaction schema validation** | **❌** | only if `transaction_validator is not None` |
| **Application-specific validation** | **callback** | via `transaction_validator` argument |

**Critical finding:** `BlockV2.verify()` treats generic transaction schema validation as optional. The caller decides whether any transaction validation runs by providing a callback. The V2 block type marker does not imply V2 transaction validation.

---

## 2. `Ledger.add_block_v2()` — `chainbreaker/chain.py:313`

**Called by:**
- `Ledger.add_block()`
- `cli_v2.v2_block_add()`
- `network/relay/engine.py:handle_block()`
- `network/sync/engine.py:handle_block()`
- tests

**Validation performed:**

| Check | Status | Notes |
|-------|--------|-------|
| Previous hash matches tip | ✅ | before any state mutation |
| Target matches expected | ✅ | before any state mutation |
| Header is `BlockHeaderV2` | ✅ | before any state mutation |
| Version == `PROTOCOL_VERSION` | ✅ | before any state mutation |
| Registry root matches replayed previous state | ✅ | before any state mutation |
| Median-past + reference-time | ⚠️ | delegated to `BlockV2.verify()` |
| PoW + Merkle | ⚠️ | delegated to `BlockV2.verify()` |
| **Generic transaction schema validation** | **callback** | delegated to `BlockV2.verify(..., transaction_validator=self.transaction_validator)`; `None` means skipped |
| **Governance transaction validation** | **✅** | `_apply_transactions()` runs `_parse_governance_transaction()` and `apply_registry_transaction()` |
| Archive/scripture transaction validation | ❌ | no special handling; falls under generic schema only |
| Witness validation | ❌ | not performed at block admission |

**Critical finding:** `add_block_v2()` passes `self.transaction_validator` (which defaults to `None`) into `BlockV2.verify()`. If the ledger was constructed without a validator, malformed transactions can pass `BlockV2.verify()` and reach `_apply_transactions()`. A malformed non-governance transaction simply returns `None` from `_parse_governance_transaction()` and is silently accepted.

---

## 3. `Ledger.mine_block_v2()` — `chainbreaker/chain.py:250`

**Called by:**
- `cli_v2.v2_block_mine()`
- `network/relay/engine.py` (indirectly, tests)
- `network/sync/engine.py` (indirectly, tests)
- many tests

**Validation performed:**

| Check | Status | Notes |
|-------|--------|-------|
| Generic transaction schema validation | **❌** | `mine_block_v2()` never calls `validate_transaction()` |
| Governance transaction validation | ❌ | no state application during mining |
| Archive/scripture validation | ❌ | none |
| Witness validation | ❌ | none |
| Registry root | ✅ | computed from previous replayed state |
| Merkle root | ✅ | computed from transaction hashes |
| PoW | ✅ | `block.mine()` |

**Critical finding:** `mine_block_v2()` does not validate transactions at all. It is possible to mine a V2 block containing a malformed transaction that would then be accepted by `add_block_v2()` if the ledger also lacks a validator.

**Differential review:** `mine_block()` (V1) *does* call `validate_transaction(tx)` for every transaction before mining. `mine_block_v2()` lacks this call. This is accidental validation asymmetry, not an intentional V1/V2 boundary.

---

## 4. `Ledger.validate_chain()` — `chainbreaker/chain.py:355`

**Called by:**
- `cli.py` (`chainbreaker validate`)
- `cli_v2.py` (`chainbreaker v2 validate`)
- tests

**Validation performed:**

| Check | Status | Notes |
|-------|--------|-------|
| Genesis integrity | ✅ | `genesis.verify(allow_genesis=True)` |
| Previous hash chain | ✅ | compares to recomputed hash |
| Difficulty retarget | ✅ | `expected_target_at(i)` |
| Median-past rule | ✅ | `median_past_time(i)` |
| PoW + Merkle | ⚠️ | delegated to `current.verify(...)` |
| Registry root commitment | ✅ | recomputed from replay |
| Registry state replay | ✅ | `_apply_transactions()` catches `RegistryError`, `GovernanceError` |
| Cache corruption detection | ✅ | compares cached vs recomputed state |
| **Generic transaction schema validation** | **callback** | delegated to `current.verify(..., transaction_validator=self.transaction_validator)`; `None` means skipped |

**Critical finding:** Same root cause as `add_block_v2()`. A ledger constructed without `transaction_validator` will replay the chain without validating transaction schemas, so a malformed non-governance transaction stored in the chain is never detected.

---

## 5. CLI `v2 block mine` — `chainbreaker/cli_v2.py:v2_block_mine`

**Path:** user JSON → `Ledger.mine_block_v2(txs)` → writes block file

| Validation | Status | Notes |
|------------|--------|-------|
| Transaction is dict | ✅ | explicit loop check |
| Generic transaction schema | **❌** | no `validate_transaction()` call |
| Governance/archive/scripture | ❌ | none |

**Critical finding:** The CLI allows a user to produce a malformed V2 block file. If that block is later added through any path, the validation gap propagates.

---

## 6. CLI `v2 block add` — `chainbreaker/cli_v2.py:v2_block_add`

**Path:** block file → `BlockV2.from_dict()` → structural checks → `Ledger.add_block_v2()`

| Validation | Status | Notes |
|------------|--------|-------|
| Protocol version | ✅ | explicit check |
| Previous hash | ✅ | explicit check |
| Target | ✅ | explicit check |
| Registry root | ✅ | explicit check |
| Full consensus via `add_block_v2()` | ✅ | returns `False` on rejection |
| **Generic transaction schema** | **callback** | depends on ledger's `transaction_validator` |

Same root cause: ledger loaded without validator bypasses transaction schema checks.

---

## 7. Network sync ingestion — `chainbreaker/network/sync/engine.py:handle_block`

**Path:** `BlockMessage.from_payload()` → `BlockSync.parse_block_message()` → `Ledger.add_block_v2(block)`

| Validation | Status | Notes |
|------------|--------|-------|
| Header parsing | ✅ | `parse_block_message()` enforces height/prev-hash |
| Full ledger validation | ✅ | `add_block_v2()` returns `False` on rejection |
| **Generic transaction schema** | **callback** | depends on ledger's `transaction_validator` |
| Storage commit | ✅ | only after `add_block_v2()` succeeds |

**Critical finding:** A sync engine constructed with a ledger that has no `transaction_validator` will accept blocks containing malformed non-governance transactions, persist them via `StorageBackend.append_block()`, and advance HEAD.

---

## 8. Network relay ingestion — `chainbreaker/network/relay/engine.py:handle_block`

**Path:** `BlockMessage.from_payload()` → `_decode_block()` → hash check → `Ledger.add_block_v2(block)` → storage append

| Validation | Status | Notes |
|------------|--------|-------|
| Decoded block hash matches announced hash | ✅ | before consensus |
| Duplicate suppression | ✅ | seen cache |
| Full ledger validation | ✅ | `add_block_v2()` |
| Storage commit | ✅ | after consensus acceptance |
| **Generic transaction schema** | **callback** | depends on ledger's `transaction_validator` |

**Critical finding:** Same as sync. Relay path depends entirely on the ledger's optional validator.

---

## 9. Storage restore / replay paths

### 9a. `FlatFileStorageBackend.append_block()` — `chainbreaker/storage/backend.py`

**Called by:** sync `_commit()`, relay `handle_block()`

| Validation | Status | Notes |
|------------|--------|-------|
| Replay registry transactions | ⚠️ | only governance `register`/`rotate`/`revoke` with **incorrect type lookup** (reads `body.get("type")` instead of `tx.get("type")`) |
| Header hash verification | ✅ | staged hash must match block hash |
| Atomic journal commit | ✅ | durable before HEAD update |
| Generic transaction schema | ❌ | storage does not validate transaction schema |

**Discovered risk (separate from 8M-A scope):** `append_block()` checks `body.get("type")` against `"register"`, `"rotate"`, `"revoke"`, but CLI/ledger produce governance transactions with `tx["type"] == "governance"` and `body["action"] == "curator_register"`. This means storage replay currently skips governance state updates. This is a real bug but is outside the 8M-A transaction-schema-validation gap and should be fixed in a follow-up or under a broader storage replay hardening task. **Do not change this under 8M-A without explicit authorization.**

### 9b. `FlatFileStorageBackend.read_chain_up_to()` — `chainbreaker/storage/backend.py`

| Validation | Status | Notes |
|------------|--------|-------|
| Reads canonical blocks | ✅ | from disk |
| Reconstructs genesis | ✅ | from constants |
| Generic transaction schema | ❌ | no validation on read |

### 9c. `Ledger.from_dict()` / `Ledger.__init__` chain replay

| Validation | Status | Notes |
|------------|--------|-------|
| Replays registry states | ✅ | `_replay_registry_states()` |
| Validates genesis | ⚠️ | `genesis.verify(allow_genesis=True)` |
| Generic transaction schema | **callback** | no baseline validation unless `transaction_validator` provided |

---

## 10. `mine_block()` vs `mine_block_v2()` differential review

| Aspect | `mine_block()` (V1) | `mine_block_v2()` (V2) |
|--------|---------------------|------------------------|
| Calls `validate_transaction()` | ✅ | ❌ |
| Allows coinbase injection | ✅ | ❌ (no coinbase concept) |
| Computes registry root | N/A | ✅ |
| Returns type | `Block` | `BlockV2` |
| Validated by `add_block()` | V1 path only | V2 path only |

**Conclusion:** The absence of `validate_transaction()` in `mine_block_v2()` is **accidental asymmetry**, not an intentional V1/V2 compatibility boundary. V2 still needs generic transaction schema validation.

---

## 11. Summary of vulnerable paths

| Path | Can malformed non-governance tx reach state/storage? | Root cause |
|------|--------------------------------------------------------|------------|
| `mine_block_v2()` → write block file → later `add_block_v2()` | **Yes** | no `validate_transaction()` during mining |
| `Ledger.add_block_v2()` with default ledger | **Yes** | `transaction_validator=None` skips validation in `BlockV2.verify()` |
| `Ledger.validate_chain()` with default ledger | **Yes** | same optional callback |
| CLI `v2 block mine` | **Yes** | no transaction schema validation |
| CLI `v2 block add` | **Yes** | default ledger has no validator |
| Sync `handle_block` | **Yes** | default ledger has no validator |
| Relay `handle_block` | **Yes** | default ledger has no validator |

---

## 12. Architecture chosen for 8M-A

The smallest change that closes the gap without duplicating validators:

1. **Make `validate_transaction()` mandatory inside `BlockV2.verify()`** for any non-genesis V2 block. Remove the `transaction_validator is None` short-circuit for V2.
2. **Keep `transaction_validator` as an optional additional hook** for application-specific checks (e.g., archive witness counts, monetary rules in the future). It layers on top of baseline schema validation.
3. **Call `validate_transaction()` in `Ledger.mine_block_v2()`** before mining, matching the V1 behavior.
4. **Do not change `_add_block_v1()` or `Block.verify()`** — V1 remains on the optional callback path as a deprecated compatibility boundary.
5. **All ingress paths** (`add_block_v2`, sync, relay, CLI) automatically inherit mandatory validation because they all converge on `BlockV2.verify()`.

This design:
- makes baseline V2 schema validation non-optional,
- preserves the ability to add application-specific validators,
- does not duplicate logic across network/sync/relay/CLI,
- keeps governance validation layered in `_apply_transactions()` on top of generic validation,
- keeps archive/scripture witness validation as a future application layer on top of generic schema.

---

## 13. Open questions before implementation

1. Does making `validate_transaction()` mandatory inside `BlockV2.verify()` break any existing test that relies on a malformed transaction reaching `_apply_transactions()`? We will run the full test suite and add regression tests to confirm.
2. Does `validate_transaction()` reject any currently-accepted valid V2 transaction? We will verify against existing test vectors.
3. Does `mine_block_v2()` now need to handle `SchemaError` gracefully (return `False` or raise `LedgerError`)? The V1 path raises `SchemaError` directly from `validate_transaction()`. We will mirror that behavior.
