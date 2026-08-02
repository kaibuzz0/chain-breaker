# Registry State Adversarial Review

Phase: **5C  Registry State Machine Adversarial Testing**  
Branch: `registry-governance-hardening`  
Status: design-only before code changes

---

## Goal

Find any way to make two honest nodes derive different registry states from
the same block history, or to make one node accept an invalid state transition.

---

## Attack model

The attacker controls the raw bytes and transaction ordering inside blocks, but
not the honest node's code.  The honest node must:

1. Accept only valid state transitions.
2. Reject invalid ones deterministically.
3. Produce identical final registry state for identical input history.

---

## Targets

### 1. Transaction ordering

`apply_registry_transaction` is called once per transaction in strict list
order.  Ordering matters because later transactions may depend on earlier ones.

Attack cases:

- `register(alice)` then `register(bob)` vs reverse order: should produce same state.
- `register(alice)` then `rotate(alice)` vs reverse: reverse must fail because
  rotate requires an existing active key.
- `register(alice)` then `revoke(alice)` vs reverse: reverse must fail.
- Two registrations of the same `curator_id` in one block: must fail.
- Two registrations of the same `public_key` for different curators: must fail.

### 2. Replay attacks

A valid governance transaction includes `previous_registry_root` and is
considered idempotent only if it is byte-for-byte identical and the state is
identical.  Replay against a different state must fail.

Attack cases:

- Same register transaction included in block 1 and block 2.
- Same transaction with a different `previous_registry_root`.
- Same transaction after the curator already exists.
- Replayed rotation with old `previous_registry_root`.

### 3. Activation boundary attacks

The rule is `activation_height > block_height`.  A record becomes active at
`activation_height`.

Attack cases:

- `activation_height == block_height` (invalid, must reject).
- `activation_height == block_height + 1` (valid).
- `activation_height` far in the future.
- `activation_height == 0`.
- Negative `activation_height` (parser rejects).
- `activation_height` at integer overflow boundary.

### 4. State corruption attacks

The `Ledger` caches `registry_states` by height, but the cache must be a pure
optimization.  Corrupting the cache must be detected by replay.

Attack cases:

- Directly mutate `ledger.registry_states[H]` after it is computed.
- Delete intermediate states.
- Replace a state with an older version.
- Verify that `validate_chain()` recomputes and catches the mismatch.

### 5. Determinism testing

Two independent `Ledger` instances with the same chain must produce identical
states.  Two separate Python processes must produce identical roots.

### 6. Failure isolation

A failed governance transaction inside a block must reject the whole block.  No
partial state mutation may survive.

---

## Test plan

Add `tests/test_adversarial_registry_state.py` with tests covering each target.

---

## Success criteria

- Same history always yields same state and same root.
- Invalid ordering/replay/boundary conditions are rejected.
- Cache corruption is detected by replay.
- Failed transactions leave no state change.
- All existing gates continue to pass.
