# Consensus Change Policy

## Scope

This policy applies to any change in the following files that affects canonical
encoding, validation, proof-of-work, governance, registry-state commitment,
attestation semantics, or chain progression:

- `chainbreaker/block.py`
- `chainbreaker/chain.py`
- `chainbreaker/codec.py`
- `chainbreaker/crypto.py`
- `chainbreaker/governance.py`
- `chainbreaker/registry_state.py`
- `chainbreaker/witness.py`

## Marking

Consensus-critical modules and functions are marked with:

```python
# CONSENSUS-CRITICAL
```

A marker at the top of a module means the entire module is in scope. A marker
above a specific function or expression means that local change is in scope.

## Required review for consensus changes

Before merging a change to a consensus-critical area, the author must confirm:

1. **Protocol compatibility review**
   - Does the change preserve or intentionally update Protocol V2 semantics?
   - Is the change backward-compatible with existing frozen vectors?

2. **Frozen-vector review**
   - Run `python test-vectors/validate_vectors.py`.
   - If the change is intentional and alters canonical output, update frozen
     vectors only after cross-language review.

3. **Regression tests**
   - Add or update a test that fails before the fix and passes after it.
   - Prefer tests that assert an invariant rather than a snapshot of current
     output.

4. **Cross-language impact assessment**
   - If the change affects Header V2, SHA-256d, PoW, Merkle, registry-state
     encoding, governance, or attestations, also run the Rust verifier:
     `cargo run --manifest-path rust-verifier/Cargo.toml -- verify test-vectors`
   - Update `rust-verifier` if it must be kept in sync.

## Prohibited shortcuts

The following are not acceptable ways to make CI pass:

- Weakening an assertion to accept more inputs.
- Removing a `raise` or validation check without a protocol-level reason.
- Changing frozen expected values to match a buggy implementation.
- Skipping the Rust verifier when the changed code is covered by it.

## Regression tools

On any consensus-related PR, run at least:

```bash
pytest tests/ -q
python test-vectors/validate_vectors.py
cargo run --manifest-path rust-verifier/Cargo.toml -- verify test-vectors
ruff check chainbreaker tests
mypy chainbreaker
```

For releases or significant refactors, also run the full mutation-testing
campaign documented in `docs/CONSENSUS_MUTATION_RESULTS.md`.
