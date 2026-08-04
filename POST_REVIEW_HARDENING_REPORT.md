# Post-Review Hardening Report

**Branch:** `registry-governance-hardening`  
**Previous HEAD:** `6cb725accec8d504a8b8e53ecbeefe1cb3857d4f`  
**Integration base:** `39ff13da30ea6ad13d6b1b24b89dfc79b7b36952`  
**Date:** 2026-08-02

---

## Findings fixed

### HIGH 1: `header.version` not enforced

**Problem:** `BlockV2.verify()` and `Ledger.add_block_v2()` accepted v2-shaped
blocks whose `header.version` was not `2`. This violated the protocol invariant
that a v2 block must identify itself as v2.

**Fix:**

* Added `if self.header.version != PROTOCOL_VERSION: return False` at the top
  of `BlockV2.verify()` in `chainbreaker/block.py`.
* Added the same check in `Ledger.add_block_v2()` in `chainbreaker/chain.py`.
* Imported `PROTOCOL_VERSION` into `chainbreaker/chain.py`.

**Regression tests:**

* `tests/test_post_review_hardening.py::test_v2_header_wrong_version_rejected`
* `tests/test_post_review_hardening.py::test_v2_header_correct_version_accepted`

---

### HIGH 2: `validate_chain()` used wall-clock time

**Problem:** `Ledger.validate_chain()` called `int(time.time()) + 7200` to
reject blocks too far in the future. Two nodes with different clocks could
reach different validity decisions for the same chain, breaking the
determinism invariant.

**Fix:**

* Removed the future-timestamp check from `validate_chain()` in
  `chainbreaker/chain.py`.
* `BlockV2.verify()` still accepts an optional `reference_time` parameter for
  local policy checks, but the canonical replay path no longer depends on the
  system clock.

**Regression tests:**

* `tests/test_post_review_hardening.py::test_validate_chain_deterministic_without_system_clock`
* `tests/test_post_review_hardening.py::test_validate_chain_cross_process_determinism`

---

### HIGH 3: Transaction ID depended on signature ordering

**Problem:** Governance transaction IDs were computed from `to_dict()` output,
which preserves the order of `governance_signatures`. Reordered signatures
would produce a different transaction ID, causing `registration_txid` and the
registry root to differ for the same logical action.

**Fix:**

* Added `_canonical_txid()` helper in `chainbreaker/chain.py` that sorts
  `governance_signatures` by `key_index` ascending before hashing.
* Updated `Ledger._apply_transactions()` to use `_canonical_txid()`.
* Documented canonical signature ordering in `docs/PROTOCOL.md` Section 9.5.

**Regression tests:**

* `tests/test_post_review_hardening.py::test_governance_transaction_signature_order_is_canonical`
* `tests/test_post_review_hardening.py::test_governance_signature_ordering_determines_state_root`

---

## Documentation fixes

| Document | Fix |
|----------|-----|
| `docs/CONSENSUS_INVARIANTS.md` | Chain-work formula corrected to `floor(MAX_TARGET / block.target)` |
| `docs/HEADER_V2_DESIGN.md` | Genesis root now references `RegistryState.genesis(...)` (Model B) |
| `docs/HEADER_V2_DESIGN.md` | Type marker corrected to `0x02` |
| `docs/HEADER_V2_TEST_VECTORS.md` | Type marker corrected to `0x02` |
| `docs/PROTOCOL.md` | Target field byte-order wording clarified |
| `docs/PROTOCOL.md` | Added registry-state record/governance-key sorting rules |
| `docs/PROTOCOL.md` | Added Section 9.5 canonical signature ordering |

---

## Files changed

* `chainbreaker/block.py`
* `chainbreaker/chain.py`
* `chainbreaker/registry_state.py`
* `docs/CONSENSUS_INVARIANTS.md`
* `docs/HEADER_V2_DESIGN.md`
* `docs/HEADER_V2_TEST_VECTORS.md`
* `docs/PROTOCOL.md`
* `tests/test_post_review_hardening.py` (new)

---

## Verification results

| Gate | Result |
|------|--------|
| `pytest -v` | **691 passed** |
| `pytest --cov=chainbreaker --cov-report=term-missing` | **84%** total |
| `ruff check chainbreaker tests` | passed |
| `mypy chainbreaker` | passed |
| `python -m build` | passed |
| `pip-audit -r requirements.txt` | no known vulnerabilities |
| `bandit -r chainbreaker` | no issues |

**Dependency note:** `pip-audit` initially reported 3 CVEs in `cryptography 48.0.1`
(CVE-2026-69248, CVE-2026-69247, CVE-2026-69249). The dependency was bumped to
`cryptography>=50.0.0,<51` in `pyproject.toml` and `requirements.txt`, and the
audit was re-run clean.

---

## Remaining deferred risks

* Governance keys remain static; no rotation mechanism exists. Documented as
  alpha limitation.
* Default genesis governance keys are placeholders and must be replaced before
  any real network.
* `Ledger.from_dict` uses a heuristic to decide v1 vs v2; not used for network
  consensus input.
* `mine_block_v2` does not call `validate_transaction` before Merkle-root
  computation; lower priority than the consensus fixes above.

---

## Conclusion

The three high-severity findings from the independent read-only review have
been fixed and regression-tested. The documentation has been aligned with the
implementation. The branch is ready for the next decision point.
