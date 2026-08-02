# Activation-Height Consistency Note

Date: pre-Milestone 4E  
Status: **resolved**

---

## Rule

A governance transaction included in block `H` specifies an
`activation_height` such that:

```text
activation_height > H
```

The transaction is **recorded** in registry state as of block `H`.

The affected curator/key becomes **active** for attestations at block heights:

```text
H' >= activation_height
```

## Why this rule

This gives the network one block of notice before a new key is authoritative.
It also prevents a transaction from authorizing itself: a `curator_register`
included in block `H` cannot be used to sign attestations within the same block
because the key is not yet active.

## Documents updated

- `docs/PROTOCOL.md` — Section 9.3 already states this rule.
- `docs/REGISTRY_ROOT_VALIDATION_DESIGN.md` — Section 5 corrected to match.
- `chainbreaker/registry_state.py` — reducer enforces
  `activation_height > block_height`.
- `tests/test_registry_state.py` — boundary tests exercise this rule.
- `tests/test_registry_validation.py` — block-level tests use
  `activation_height = H + 1`.

## Implication for 4E

When validating a witness attestation at block height `A`, the validator must
look up the registry state and check:

```text
record.activation_height <= A < record.revocation_height
```

with the convention that `revocation_height = None` means "not revoked."

A registration in block `H` with `activation_height = H + 1` is therefore first
usable at height `H + 1`.
