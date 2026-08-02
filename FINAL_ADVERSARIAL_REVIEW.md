# Final Adversarial Review

Phase: **5G  Final Adversarial Review**  
Repository: `kaibuzz0/chain-breaker`  
Branch: `registry-governance-hardening`  
Starting HEAD: `20e939f`

---

## 1. Executive Summary

### Protocol v2 purpose

Protocol v2 (`chainbreaker-scripture-v2`) is a deterministic curator-registry
governance layer for the Chain Breaker scripture-anchoring system. It introduces:

* a fixed genesis governance key set committed inside the genesis registry state;
* threshold governance signatures for all registry mutations;
* ledger-derived registry state, recomputed from genesis on every validation;
* block-header commitments (`registry_root`) to the registry state after the
  previous block;
* historical attestation validation against the registry state at the
  attestation height.

### Consensus architecture

```text
genesis registry state
        |
        v
block 0  registry_root = hash(genesis state)
        |
        v
block N  registry_root = hash(state after applying blocks 0..N-1)
        |
        +-- governance transactions (register / rotate / revoke)
        +-- archive transactions with curator witnesses
        |
        v
historical state at height H  <--  used to validate attestations at H
```

The source of truth is always the chain history, not local cache or memory.

### Adversarial testing completed

| Phase | Focus | Result |
| ----- | ----- | ------ |
| 5A | Serialization attacks | 1 bug found and fixed |
| 5B | Governance authorization | Authority commitment strengthened |
| 5C | Registry state machine | 3 high-severity bugs found and fixed |
| 5D | Fork divergence | No new bugs; model survived |
| 5E | Data corruption | No new bugs; safe rejection confirmed |
| 5F | Fuzz testing | No new bugs; no crashes or hangs |

### Confidence level

**Moderate-to-high for the tested scope.** The consensus-critical paths for
header parsing, registry-state derivation, governance authorization, historical
attestation, fork simulation, corruption handling, and random fuzzing have all
passed adversarial testing. Several high-severity bugs were found and fixed
before this review.

### Remaining limitations

* No independent cryptographic audit.
* No production P2P network or live deployment testing.
* No formal verification.
* No production-grade reorganization engine.
* No large-scale performance or denial-of-service testing.

---

## 2. Complete Attack Surface Review

### Serialization

**Covered:**

* `encode_header_v2` / `decode_header_v2`
* canonical 149-byte v2 header layout
* trailing-byte handling
* truncated and oversized headers
* random byte mutations

**Findings:**

* `decode_header_v2` originally accepted trailing bytes.
* Fixed by adding `strict=True` canonical mode that requires exactly 149 bytes
  and consumes the entire input.

### Governance

**Covered:**

* threshold signature validation
* register / rotate / revoke semantics
* replay attacks
* signature mutations
* unknown signers
* duplicate signatures
* conflicting rotations

**Findings:**

* `RegistryState.__hash__` originally omitted `governance_keys` and `threshold`,
  meaning two states with different authority models could hash equal.
* Fixed by including the complete authority model in `__hash__`.

### Registry State Machine

**Covered:**

* pure reducer `apply_registry_transaction`
* activation-height boundaries
* deterministic replay across ledgers and processes
* failed-transaction isolation
* cache corruption

**Findings:**

1. **Cache trust vulnerability:** `Ledger.validate_chain()` and `mine_block_v2()`
   used the `registry_states` cache as authoritative. A corrupted cache could make
   a node accept blocks with mismatched `registry_root`.
   * **Fix:** replay from genesis is now authoritative; cache is used only as a
     non-trusted performance aid.
2. **Governance authority loss:** `_apply_rotate()` and `_apply_revoke()` returned
   `RegistryState(records=...)` without preserving `governance_keys` and
   `threshold`, causing authority to disappear after state transitions.
   * **Fix:** all reducer paths now preserve the full authority model.
3. **Historical key lookup bug:** `_require_active_record()` selected the newest
   record by `curator_id` even when that record was not yet active.
   * **Fix:** the helper now selects the record matching the supplied key and
     activation window.

### Fork Behavior

**Covered:**

* competing valid branches
* common-ancestor state equality
* branch-specific registry roots
* chain-work selection
* reorg-style branch switching
* cache isolation between ledgers

**Findings:**

* No new consensus failures. Competing histories maintain independent,
  deterministic state and do not contaminate each other.

### Corruption

**Covered:**

* modified header fields (prev_hash, merkle_root, registry_root, timestamp)
* truncated / mutated / oversized block bytes
* corrupted cached registry states
* invalid governance signatures and fields
* invalid witness signatures and heights
* malformed public keys
* missing required fields

**Findings:**

* No new bugs. All corrupted inputs were rejected deterministically without
  partial state updates, cache mutation, or crashes.

### Fuzzing

**Covered:**

* 100 random seeds of header decoding fuzzing
* 100 random `BlockHeaderV2.from_dict()` calls
* 100 random `RegistryState` constructions
* 50 random governance transaction dicts
* 50 random attestation dicts
* cross-ledger and cross-process determinism
* 10 KB input to confirm no hang

**Findings:**

* No crashes, no hangs, no unsafe exceptions. Identical inputs produced
  identical validation results across independent ledgers and processes.

---

## 3. Vulnerability History

| Issue | Severity | Component | Fix |
| ----- | -------- | --------- | --- |
| Header decoder accepted trailing bytes | Medium | `chainbreaker/codec.py` | Added `strict=True` canonical mode to `decode_header_v2` |
| `RegistryState.__hash__` omitted authority | High | `chainbreaker/registry_state.py` | Include `governance_keys` and `threshold` in state hash |
| Ledger trusted corrupted registry cache | High | `chainbreaker/chain.py` | Replay from genesis is authoritative; cache is non-trusted |
| Reducer dropped governance authority | High | `chainbreaker/registry_state.py` | Preserve `governance_keys` and `threshold` in all state transitions |
| Historical record lookup ignored activation | Medium | `chainbreaker/registry_state.py` | Select record by key + activation window |

---

## 4. Remaining Risks

* **No external cryptographic audit.** Ed25519 and SHA-256 usage are standard,
  but an independent audit would increase confidence.
* **No production P2P network.** Consensus logic is local-only; network-level
  attacks, eclipse attacks, and propagation races are out of scope.
* **No large-scale deployment testing.** Behavior under high throughput, large
  state, and long chain histories has not been stress-tested.
* **No formal verification.** The reducer and serialization have not been
  mathematically proven correct.
* **No production reorganization engine.** Fork selection exists via chain-work,
  but a full reorg handling and rollback engine is not implemented.
* **Coverage gaps.** Legacy v1 code paths, CLI, and archive tooling have lower
  test coverage than the new consensus modules.

---

## 5. Consensus Guarantees

The following properties have been tested and are enforced by the current code:

* **Deterministic replay.** Any node with the same genesis and chain history
  computes the same registry state and registry root.
* **Deterministic registry roots.** The `registry_root` in each block header
  commits to the registry state produced by all prior blocks.
* **Canonical serialization.** V2 headers serialize to exactly 149 bytes with a
  strict decoder mode.
* **Historical validation.** Attestations are verified against the registry
  state at the attestation block height, respecting rotations and revocations.
* **Fork isolation.** Competing branches maintain independent states and roots;
  no state leaks between ledgers.
* **Corruption rejection.** Malformed headers, transactions, witnesses, and
  cached states are rejected without partial updates or crashes.

---

## 6. Final Verification

### Local checkout

* Branch: `registry-governance-hardening`
* HEAD: `20e939f`
* Working tree: clean

### Test results

| Gate | Result |
| ---- | ------ |
| `pytest -v` | **685 passed** |
| `pytest --cov=chainbreaker --cov-report=term-missing` | **coverage reported** |
| `ruff check chainbreaker tests` | pass |
| `mypy chainbreaker` | pass |
| `python -m build` | pass |
| `pip-audit -r requirements.txt` | no known vulnerabilities |
| `bandit -r chainbreaker` | no issues |

### Fresh clone verification

A separate fresh clone at `D:/Hermes-USB-Portable-main/src/chain-breaker-fresh-review`
was used during earlier milestones to verify clean-install behavior and will be
re-verified as part of this phase.

---

## 7. Conclusion

Phase 5 adversarial hardening is complete. Several high-severity consensus bugs
were discovered and fixed before this final review. The remaining risk lies
primarily in untested operational surfaces (networking, scale, formal
verification, external audit). The protocol v2 consensus core is ready for
human-maintainer review and, pending that review, a pull request.
