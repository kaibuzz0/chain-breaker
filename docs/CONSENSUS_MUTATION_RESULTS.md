# Consensus Mutation Testing Results

## Summary

A targeted mutation campaign was run against the consensus-critical modules of
Chain-Breaker Protocol V2. The goal was to verify that accidental weakening of
consensus rules is detected by the existing Python test suite, frozen vectors,
and the independent Rust verifier.

| Metric | Value |
|---|---:|
| Commit tested | `ac5e7583c2b1062f2c099a85d0c38fa86d798417` |
| Branch | `phase7d-consensus-mutation-testing-2` |
| GitHub Actions run | `31223253093` |
| Runner | `ubuntu-latest` |
| Total intended mutations | 33 |
| Executed | 33 |
| Killed | 20 |
| Survived | 0 |
| Apply errors | 12 |
| Timeouts | 1 |
| Excluded | 0 |
| Equivalent | 0 |
| Mutation score | 60.6% |
| Runtime | ~24 minutes 43 seconds |

**Important:** the 60.6% score does **not** mean 60.6% of dangerous mutations
were proven safe. It means 20 of 33 attempted mutations were successfully
applied and killed. Twelve mutations could not be applied uniquely by the
string-replacement harness, and one mutation caused a timeout. Those 13 cases
are **coverage gaps**, not passes.

## Verification gates

Each applied mutation was evaluated against:

1. `pytest tests/ -q`
2. `python test-vectors/validate_vectors.py`
3. `cargo run --manifest-path rust-verifier/Cargo.toml -- verify test-vectors`

A mutation was classified as **killed** if any gate failed.

## Killed mutations (20)

All 20 successfully applied dangerous mutations were killed by at least one
verification gate.

| # | Module | Mutation | Detected by | Notes |
|---|--------|----------|-------------|-------|
| 1 | `block.py` | `<=` → `<` in `satisfies_pow` | Python vectors, Rust verifier | PoW target comparison |
| 2 | `block.py` | header length `!= 149` → `!= 148` | pytest, Python vectors, Rust verifier | exact header V2 length |
| 3 | `block.py` | genesis version check bypassed | pytest, Python vectors, Rust verifier | version enforcement |
| 4 | `block.py` | genesis `prev_hash` mismatch allowed | pytest, Python vectors, Rust verifier | canonical genesis |
| 5 | `chain.py` | V2 version enforcement ignored | Python vectors, Rust verifier | chain version gate |
| 6 | `chain.py` | registry-root mismatch ignored | Python vectors, Rust verifier | state continuity |
| 7 | `chain.py` | canonical signature sorting disabled | pytest, Python vectors, Rust verifier | txid canonicalization |
| 8 | `chain.py` | MTP `<=` → `<` | Python vectors, Rust verifier | median-past-time rule |
| 9 | `codec.py` | little-endian → big-endian | pytest, Python vectors, Rust verifier | header byte order |
| 10 | `codec.py` | short hashes allowed | pytest, Python vectors, Rust verifier | exact hash length |
| 11 | `codec.py` | non-canonical varints allowed | Python vectors, Rust verifier | minimal varint encoding |
| 12 | `crypto.py` | SHA-256d → single SHA-256 | pytest, Python vectors, Rust verifier | hash primitive |
| 13 | `governance.py` | threshold `<` → `<=` | pytest, Python vectors, Rust verifier | multi-sig threshold |
| 14 | `governance.py` | short signatures allowed | Python vectors, Rust verifier | Ed25519 signature length |
| 15 | `registry_state.py` | unsorted records in state root | pytest, Python vectors, Rust verifier | canonical state ordering |
| 16 | `registry_state.py` | unsorted genesis keys | Python vectors, Rust verifier | canonical genesis ordering |
| 17 | `registry_state.py` | registry root single → double SHA-256 | pytest, Python vectors, Rust verifier | state commitment hash |
| 18 | `registry_state.py` | use current key instead of historical | pytest, Python vectors, Rust verifier | historical key lookup |
| 19 | `witness.py` | ignore witness height mismatch | Python vectors, Rust verifier | height binding |
| 20 | `witness.py` | attestation V2 version 2 → 1 | Python vectors, Rust verifier | domain version |

## Apply errors (12)

These intended mutations were not exercised because the source text did not match
the expected pattern exactly once. They are coverage gaps in the harness, not
survivors.

| # | Module | Intended mutation | Classification | Notes |
|---|--------|-------------------|----------------|-------|
| 1 | `block.py` | allow target below `MIN_TARGET` | harness too brittle | pattern changed or duplicated |
| 2 | `block.py` | skip merkle root check | harness too brittle | `if False:` replacement ambiguous |
| 3 | `chain.py` | ignore previous-hash link | harness too brittle | pattern not unique |
| 4 | `chain.py` | ignore target expectation | harness too brittle | pattern not unique |
| 5 | `codec.py` | accept wrong header type marker | harness too brittle | `if False:` replacement ambiguous |
| 6 | `crypto.py` | target conversion big → little endian | harness too brittle | `int.from_bytes(raw, "big")` appears in multiple contexts |
| 7 | `governance.py` | allow duplicate key indices | source changed | `seen` set logic not in expected form |
| 8 | `governance.py` | ignore wrong network_id | harness too brittle | `if False:` replacement ambiguous |
| 9 | `governance.py` | ignore schema version | harness too brittle | `if False:` replacement ambiguous |
| 10 | `registry_state.py` | ignore previous_registry_root mismatch | harness too brittle | `if False:` replacement ambiguous |
| 11 | `registry_state.py` | allow activation_height `<=` block_height | source changed | comparison appears in multiple places |
| 12 | `witness.py` | omit `block_height` from attestation V2 preimage | source changed | JSON-field pattern not unique |

## Timeout (1)

| Module | Mutation | Likely cause |
|--------|----------|--------------|
| `crypto.py` | target encoding little → big endian | unknown |

The timeout occurred during the `pytest` gate. The mutation changes how the
256-bit target is encoded from integer to bytes. This likely caused either an
extremely hard or invalid target that made PoW mining hang, or it created a
near-infinite loop in a test that repeatedly mines until a valid nonce is
found. Because the run exceeded the 600-second per-mutation budget, the harness
timed out rather than confirming the mutation was killed.

**Status:** not classified as killed. A bounded regression test that exercises
target encoding with a fixed, easy target is needed before this mutation can
be reliably evaluated.

## Survivors

Zero mutations survived all verification gates. There are no dangerous survivors
requiring immediate regression tests.

## Coverage limitations

- The string-replacement harness is brittle. Twelve intended mutations failed
to apply because source patterns were not unique or the code had drifted from
when the mutations were authored.
- One mutation timed out, leaving its kill status unconfirmed.
- The mutation score of 60.6% is a harness coverage metric, not proof that the
remaining 39.4% of intended mutations are safe.
- Mutations were limited to the seven consensus-critical modules. CLI,
archival, and storage code were not covered.

## Recommended future harness improvements

1. Migrate from raw string replacement to AST-based or line/function-scoped
   mutation for the 12 apply-error cases so they are actually exercised.
2. Add a bounded, fixed-target regression test for target encoding so the
   big-endian target mutation can be evaluated without timing out.
3. Record per-mutation runtime to identify slow or hanging cases before a full
   campaign.

## Recommended CI policy

| Trigger | Job | Required |
|---|---|---|
| Every PR / push | Python pytest + Rust frozen vectors | yes |
| PR touching `chainbreaker/*.py` | mutation smoke (curated high-risk subset) | yes |
| Release / major refactor / scheduled | full targeted mutation campaign | manual gate |
| Full `mutmut` run | optional, review noise vs. value | not on every PR |

## Source code changes

No Protocol V2 consensus behavior was changed as a result of this campaign.
The only source changes in Phase 7D were:

- Addition of `# CONSENSUS-CRITICAL` module markers.
- Addition of `mutmut` as a dev dependency.
- Addition of the targeted mutation runner and workflow.
- A trailing-newline hotfix (PR #25) for lint cleanliness.

## Regressions added

None. All successfully applied dangerous mutations were already killed by the
existing verification stack.
