# Chain-Breaker Consensus Invariants

Version: `chainbreaker-scripture-v2`  
Status: **alpha prototype, not production-ready**

This document defines the invariants that every Chain-Breaker v2 implementation
must preserve, independent of language, platform, or deployment.  They are the
contracts that make fork choice, historical validation, and cross-node
agreement possible.

This is a design document.  It does not authorize a production deployment.

---

## 1. Determinism

For any sequence of blocks `B[0..N]` the canonical state is a pure function of
that sequence.

```text
State(B[0..N]) = f(Genesis, B[0], B[1], ..., B[N])
```

The function `f` must not depend on:

* wall-clock time
* filesystem contents outside the validated chain
* random values
* node configuration files
* network messages
* in-memory caches that are not reproducible from the chain

If two honest nodes receive the same block sequence, they must compute the
same state.

---

## 2. Block sequence validity

A block sequence `B[0..N]` is valid only if every block `B[i]` is valid with
respect to `State(B[0..i-1])`.

```text
valid(B[0..N])  <=>  valid(B[0]) AND valid(B[1]|State(B[0])) AND ...
                     valid(B[N]|State(B[0..N-1]))
```

A block is never validated in isolation.

---

## 3. Header commitment invariant

The block header of `B[N]` must contain a `registry_root` field that is the
hash of the canonical registry state *before* applying `B[N]`.

```text
B[N].header.registry_root == registry_root(State(B[0..N-1]))
```

The registry state at the end of `B[N]` is:

```text
State_after(B[N]) = apply_registry_transactions(
                        State(B[0..N-1]),
                        governance_transactions(B[N]),
                        height=N
                    )
```

The header commits to the *starting* state of the block, not the *ending* state.
This makes light-client verification straightforward and avoids circular
reasoning between the Merkle root and registry mutations inside the same block.

---

## 4. Registry state reducer invariant

The registry reducer is a pure function.

```text
apply_registry_transaction(state, tx, height, context) -> state'
```

For the same inputs it must always produce the same output.

It must never:

* read files
* read the system clock
* use randomness
* consult a local `Registry` object that is not derived from `state`
* mutate its input

Failure of a transaction must leave the input state unchanged.

---

## 5. Historical attestation invariant

An attestation contained in block `B[H]` is valid only if the signing curator
key was active at height `H` according to `State(B[0..H-1])`.

```text
valid_signature(tx, witness, H)  <=>
    witness.public_key == curator_key_at(State(B[0..H-1]), witness.curator_id, H)
```

The test must use the registry state *as of* the block containing the
attestation, not the current tip state.

This invariant guarantees that:

* a key not yet activated is invalid
* a revoked key is invalid at and after its revocation height
* a rotated key remains valid only for blocks before the new key activated
* later governance changes cannot retroactively invalidate old attestations

---

## 6. Fork independence

Two distinct valid chains that share a common prefix up to height `K` must
share the same registry state up to `K` and may diverge only after `K`.

```text
B[0..K] == C[0..K]  ==>  State(B[0..K]) == State(C[0..K])
```

The registry state of a chain branch must not leak into another branch.
Replaying either chain from genesis must reconstruct its own state exactly.

---

## 7. Chain-work fork choice

When multiple valid chains exist, the canonical chain is the one with the
highest accumulated chain work.

```text
chain_work(chain) = SUM over blocks in chain:  MAX_TARGET / (block.target + 1)
```

If two chains have equal chain work, the tie is broken by the lesser
lexicographic hash of the tip.  This rule must be deterministic and must not
depend on the order in which a node learned about the branches.

---

## 8. Genesis governance commitment

The genesis block of a v2 network commits to an initial registry state that
includes the genesis governance key set and threshold.

```text
genesis.registry_root == registry_root(RegistryState.genesis(governance_keys, threshold))
```

The genesis registry state contains:

```text
- governance_version: 1
- network_id: chainbreaker-scripture-v2
- governance_keys: list of bootstrap Ed25519 public keys, sorted lexicographically
- threshold: N where 1 <= N <= len(governance_keys)
- curators: empty
```

Governance keys are part of registry state from genesis.  They are not a
separate bootstrap constant.  This keeps all authority inside the same
state machine and avoids special-case logic after block 0.

The genesis block itself cannot contain a governance transaction that registers
these keys, because such a transaction would require signatures from keys that
are not yet committed.  Therefore the genesis specification defines the keys
as the initial state.

The genesis governance key list is immutable for the life of the network.
Changing it requires a new network genesis.

---

## 9. Governance signature coverage

Every governance transaction that changes registry state must carry enough valid
governance signatures to meet the threshold defined in the current registry
state.

```text
valid_governance(tx, state)  <=>
    count_valid_governance_signatures(tx, state.governance_keys) >= state.threshold
```

A signature is valid only if:

* it is from a key in `state.governance_keys`
* it covers the complete canonical transaction bytes excluding witness fields
* the same governance key is not used more than once in the same transaction

---

## 10. Activation and revocation timing

A curator key registered with activation height `A` is valid starting at
height `A`.

```text
key_active(curator, H)  <=>  A <= H < R  (or R is None)
```

A revocation height `R` makes the key invalid at and after `R`.

`R` must be strictly greater than `A`.

`A` must be strictly greater than the height at which the register transaction
is included.

A rotation transaction with activation height `A2` creates a new key valid from
`A2` and ends the validity of the previous key at `A2`.

---

## 11. Registry root recomputation

During historical validation, every `registry_root` in every header must be
recomputed from genesis.  A node must not trust a stored registry snapshot.

```text
for N in 1..tip:
    assert B[N].header.registry_root == registry_root(State(B[0..N-1]))
```

This is the canonical way to detect corrupted, tampered, or non-deterministic
state transitions.

---

## 12. No local override

A node must not accept a block whose registry state differs from the state
derived by replaying governance transactions from genesis, even if a local
configuration file or command-line argument claims a different curator set.

Local `Registry` objects may be used for:

* bootstrapping a known-good state during initial sync
* offline inspection tools
* testing

They must not be used for consensus validation of a block.

---

## 13. Unsupported transaction rejection

Any transaction whose `schema_version` or `action` is not supported by the
protocol version of the validating node must be rejected.

The rejection must be deterministic and must not depend on node policy
settings.

---

## 14. Network domain separation

A transaction is valid only for the `network_id` declared in its body.

A transaction with `network_id` X must be rejected on network Y, even if every
signature is technically correct.

This prevents replay across testnets, devnets, and mainnet-alpha networks.

---

## 15. Genesis incompatibility

`chainbreaker-scripture-v2` is not backward compatible with
`chainbreaker-scripture-v1`.

The block header format changed.  v1 nodes cannot parse v2 headers and v2
nodes cannot validate v1 headers.  The two networks must use independent
genesis blocks and independent network IDs.

A v2 network reset is required to activate these invariants.

---

## Violation handling

Any invariant violation means the block or chain is invalid.

The node must:

1. reject the block
2. not mutate its own canonical state
3. not relay the block as valid
4. log the violation with the block hash and height

A violation is never silently tolerated.

---

## Open questions

* Should the genesis block itself contain a governance-registration system
transaction, or should the genesis governance keys be implicit constants?
  * Current recommendation: implicit constants in the genesis specification,
    because a system transaction in genesis would need a signature from keys
    that are not yet registered.

* Should difficulty retargeting consider registry churn?
  * Current recommendation: no.  Difficulty is a separate time-based function.

* How should a node bootstrap without replaying from genesis?
  * Current recommendation: trusted checkpoint blocks that include a signed
    `registry_root` commitment.  The node still recomputes from the nearest
checkpoint rather than trusting a database.
