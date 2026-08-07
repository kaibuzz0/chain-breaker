# Consensus Mutation Test Plan

## Goal

Determine whether the existing test suite and frozen vectors detect
accidental weakening of Protocol V2 consensus rules.

The question we answer in Phase 7D:

> If a future developer accidentally changes a comparison, removes a
> canonicalization step, or weakens a validation, do our tests and frozen
> vectors catch it?

## Scope

### Consensus-critical modules

| Module | Responsibility | Why it is consensus-critical |
|--------|---------------|------------------------------|
| `chainbreaker/block.py` | Header/block construction, PoW check, genesis validation | Canonical header bytes and target comparison define valid blocks. |
| `chainbreaker/chain.py` | Chain assembly, retarget, previous-hash/registry-root verification, registry replay | Links blocks and advances state deterministically. |
| `chainbreaker/codec.py` | Binary encoding/decoding of headers, transactions, registry state | One flipped endian byte changes every hash. |
| `chainbreaker/crypto.py` | SHA-256d, Merkle tree, target conversion, Ed25519 helpers | Hash and PoW primitives. |
| `chainbreaker/governance.py` | Governance transaction parsing, signature verification, threshold checks | Registry mutations require valid multi-sig. |
| `chainbreaker/registry_state.py` | Registry state serialization, root hash, transaction application | Canonical state commitment. |
| `chainbreaker/witness.py` | Attestation preimage and verification | Attestation signatures bind to curator + height. |

Non-consensus modules such as CLI code and `archive.py` are out of scope
unless they feed canonical consensus input.

## Inventory of consensus-sensitive expressions

### `block.py`

| Expression | Invariant | Existing test | Frozen vector | Rust verifier |
|------------|-----------|---------------|---------------|---------------|
| `int(block_hash, 16) <= target` in `satisfies_pow` | PoW hash must not exceed target | `test_pow_v2.py` | `pow-target.json` negative | `check_pow` |
| `len(header_bytes) != 149` in `_validate_genesis_header` | Header V2 is exactly 149 bytes | `test_header_v2.py` | `header-v2.json` | `check_header_v2` |
| `header["version"] != 2` | Genesis must use version 2 | `test_genesis_v2.py` | `genesis.json` | `check_genesis` |
| `header["prev_hash"] != "0" * 64` | Genesis prev_hash is zero | `test_genesis_v2.py` | `genesis.json` | `check_genesis` |
| `computed_hash != expected_hash` | Genesis hash is deterministic | `test_genesis_v2.py` | `genesis.json`/`block.json` | `check_genesis`/`check_block` |
| `self.header.target <= MAX_TARGET` | Target must be within protocol bounds | `test_pow_v2.py` | `pow-target.json` | `check_pow` |
| `self.merkle_root() != self.header.merkle_root` | Block merkle root must match | `test_block.py` | `block.json` | `check_block` |
| `self.header.version != PROTOCOL_VERSION` | V2 blocks must use version 2 | `test_block.py` | `block.json` | `check_block` |

### `chain.py`

| Expression | Invariant | Existing test | Frozen vector | Rust verifier |
|------------|-----------|---------------|---------------|---------------|
| `block.header.prev_hash != expected_prev_hash` | Chain links must be contiguous | `test_chain.py` | — | — |
| `block.header.target != expected_target` | Difficulty retarget must be exact | `test_chain.py` | — | — |
| `block.header.version != PROTOCOL_VERSION` | Chain enforces version | `test_chain.py` | — | — |
| `block.header.registry_root != expected_registry_root` | Registry root must advance correctly | `test_chain.py` | `registry-state.json` | `check_registry_state` |
| `current.header.timestamp <= median` | MTP rule prevents timestamp abuse | `test_chain.py` | — | — |
| `actual_time <= 0` guard in retarget | Retarget division must be safe | `test_chain.py` | — | — |
| `governance_signatures = sorted(...)` in `_canonical_txid` | Signature order is canonical | `test_governance.py` | `governance-*.json` | `check_governance_*` |

### `codec.py`

| Expression | Invariant | Existing test | Frozen vector | Rust verifier |
|------------|-----------|---------------|---------------|---------------|
| `ENDIAN = "<"` | Header fields are little-endian | `test_codec.py` | `header-v2.json`/`genesis.json` | `check_header_v2` |
| `data[offset] != cls.TYPE_HEADER` | Header type marker must be 0x02 | `test_codec.py` | `header-v2.json` negative | `check_header_v2` |
| `len(raw) != cls.HASH_LEN` in `encode_hash` | Hashes are exactly 32 bytes | `test_codec.py` | `ed25519.json` public key | — |
| Non-canonical varint rejection | Canonical minimal varint encoding | `test_codec.py` | — | — |
| `encode_header_v2` field order | 149-byte canonical layout | `test_codec.py` | `header-v2.json` | `check_header_v2` |

### `crypto.py`

| Expression | Invariant | Existing test | Frozen vector | Rust verifier |
|------------|-----------|---------------|---------------|---------------|
| `hashlib.sha256(hashlib.sha256(data).digest()).digest()` | Double SHA-256 | `test_crypto.py` | `sha256d.json` | `check_sha256d` |
| `MerkleTree` odd-node duplication | Bottom-up binary tree with duplicate odd nodes | `test_crypto.py` | `merkle.json`, `merkle-extra.json` | `check_merkle` |
| `int.from_bytes(raw, "big")` in `hex_to_target` | Target is big-endian integer | `test_crypto.py` | `pow-target.json` | `check_pow` |
| `target.to_bytes(32, "big")` in `target_to_hex` | Target encodes to 32 big-endian bytes | `test_crypto.py` | `pow-target.json` | `check_pow` |
| Ed25519 verify strict | Signatures verified against public key | `test_crypto.py` | `ed25519.json` | `check_ed25519` |

### `governance.py`

| Expression | Invariant | Existing test | Frozen vector | Rust verifier |
|------------|-----------|---------------|---------------|---------------|
| `set(data.keys()) != {"key_index", "signature"}` | Signature object shape | `test_governance.py` | `governance-*.json` | `check_governance_*` |
| `len(sig_bytes) != 64` | Ed25519 signatures are 64 bytes | `test_governance.py` | `governance-*.json` | `check_governance_*` |
| `threshold must be 1..len(public_keys)` | Governance threshold bounds | `test_governance.py` | `governance-*.json` | `check_governance_*` |
| `valid < self.threshold` | Multi-sig threshold | `test_governance.py` | `governance-*.json` | `check_governance_*` |
| `data.get("network_id", NETWORK_ID) != NETWORK_ID` | Domain separation by network ID | `test_governance.py` | `governance-*.json` | `check_governance_*` |
| `schema_version != GOVERNANCE_SCHEMA_VERSION` | Reject unknown schema | `test_governance.py` | `governance-*.json` | `check_governance_*` |
| `governance_message` excludes witnesses | Signature covers body hash only | `test_governance.py` | `governance-*.json` | `check_governance_*` |

### `registry_state.py`

| Expression | Invariant | Existing test | Frozen vector | Rust verifier |
|------------|-----------|---------------|---------------|---------------|
| `sorted(state.records, key=lambda r: r.curator_id.encode("utf-8"))` | Canonical record order | `test_registry_state.py` | `registry-state.json` | `check_registry_state` |
| `sorted(governance_keys)` in genesis | Canonical governance key order | `test_registry_state.py` | `registry-state.json` | `check_registry_state` |
| `HashEngine.hash_single_hex(serialize_registry_state(state))` | Registry root is single SHA-256 | `test_registry_state.py` | `registry-state.json` | `check_registry_state` |
| `tx.activation_height <= block_height` | Register/rotate must be future | `test_registry_state.py` | `governance-*.json` | — |
| `tx.previous_registry_root != registry_root(state)` | State continuity | `test_registry_state.py` | `governance-register.json` | `check_governance_*` |
| `tx.revocation_height < old_record.activation_height` | Revocation must not precede activation | `test_registry_state.py` | `governance-rotate-revoke.json` | — |

### `witness.py`

| Expression | Invariant | Existing test | Frozen vector | Rust verifier |
|------------|-----------|---------------|---------------|---------------|
| `attestation_message_v2` field order | `{network_id, version, type, body_hash, curator_id, block_height}` canonical | `test_historical_attestation.py` | `attestation-v2.json` | `check_attestation` |
| `witness_height != block_height` | Attestation height binding | `test_historical_attestation.py` | `attestation-v2.json` | `check_attestation` |
| `state.key_was_valid_at(...)` | Historical key lookup | `test_historical_attestation.py` | `attestation-v2.json` | `check_attestation` |
| `curator.is_active_at(height)` | Attestation only when curator active | `test_historical_attestation.py` | `attestation-v2.json` negative | `check_attestation` |

## Mutation classes to test

### 1. Comparison weakening

Mutations:

- `<=` → `<`
- `<` → `<=`
- `==` → `!=`
- `!=` → `==`
- `>` → `>=`
- `>=` → `>`

Priority sites:

- `satisfies_pow` target comparison (`block.py`)
- Activation/revocation height comparisons (`registry_state.py`, `witness.py`)
- Version checks (`block.py`, `codec.py`, `governance.py`)
- Threshold checks (`governance.py`)
- Previous-hash and registry-root equality checks (`chain.py`, `block.py`)

### 2. Arithmetic mutation

Mutations:

- `+1` → `+0`
- `-1` removed
- Integer width changed (`to_bytes(8)` → `to_bytes(4)`)
- Target/work formula altered

Priority sites:

- Retarget arithmetic in `chain.py`
- Varint/height encoding widths in `codec.py`/`registry_state.py`

### 3. Canonicalization mutation

Mutations:

- Remove `sorted(...)`
- Reverse sort order
- Alter field order in canonical JSON/binary
- Swap endian conversion
- Accept trailing bytes
- Remove exact-length check

Priority sites:

- `sorted(governance_keys)` and `sorted(state.records, ...)` in `registry_state.py`
- `sorted(...)` for governance signatures in `chain.py`
- `encode_header_v2` field order in `codec.py`
- Canonical JSON object key order in `crypto.py`

### 4. Hash mutation

Mutations:

- SHA-256d → single SHA-256
- Hash wrong preimage
- Omit field from registry-state commitment
- Omit governance keys from genesis state
- Omit threshold from genesis state
- Omit block height from attestation preimage

Priority sites:

- `HashEngine.hash_double_*` in `crypto.py`
- `governance_message` in `governance.py`
- `serialize_registry_state` in `registry_state.py`
- `attestation_message_v2` in `witness.py`

### 5. Validation bypass

Mutations:

- Remove `raise`
- Replace rejection with `pass`
- Skip validator call
- Trust registry cache instead of replay
- Bypass previous-hash validation
- Bypass registry-root validation

Priority sites:

- `_validate_genesis_header` in `block.py`
- `add_block_v2` in `chain.py`
- `_apply_*` validators in `registry_state.py`

### 6. Boolean mutation

Mutations:

- `and` → `or`
- Negate predicates
- Weaken duplicate detection

Priority sites:

- `is_active_at` boolean composition
- Signature duplicate detection in `GovernanceContext`
- Height and key validation compound checks

### 7. Historical-state mutation

Mutations:

- Use current curator key instead of historical key
- Ignore activation window
- Ignore revocation
- Choose newest record regardless of height

Priority sites:

- `active_key_at` / `key_was_valid_at` in `registry_state.py`
- `verify_attestation_v2` in `witness.py`

### 8. Governance mutation

Mutations:

- Count duplicate signatures
- Ignore signer index
- Change threshold comparison
- Stop canonical signature ordering
- Omit previous registry root
- Omit network ID/domain binding

Priority sites:

- `GovernanceContext.verify` in `governance.py`
- `_canonical_txid` in `chain.py`
- `governance_message` in `governance.py`

## Tooling approach

We evaluate `mutmut` for targeted mutation of the consensus modules. If it
produces too much noise, we fall back to a controlled set of script-applied
mutations (sed-like replacements applied to a copy, then run against tests and
vectors) to keep the campaign deterministic and reviewable.

Constraints:

- Mutation tooling stays in `dev` optional dependencies, never runtime.
- No mutation tool is mandatory on every normal commit.
- We record runtime so we can decide on CI placement.

## Test/vector harness

For every mutation we run, in order:

1. `pytest tests/ -q`
2. `python test-vectors/validate_vectors.py`
3. `cargo run --manifest-path rust-verifier/Cargo.toml -- verify test-vectors`

A mutation is **killed** if any step fails. A mutation **survives** if all
steps pass and must then be classified as dangerous, equivalent, or excluded.

## CI design

- **Normal CI:** Python pytest + Rust verifier (already in place).
- **Mutation smoke gate:** small fixed subset of consensus-critical mutations,
  run on PRs that touch `chainbreaker/*.py`.
- **Full mutation campaign:** manual / scheduled / release gate, not per-commit.

## Survivor classification

| Class | Meaning | Action |
|-------|---------|--------|
| **A. Dangerous survivor** | Semantic behavior weakened; tests did not catch it | Add regression test. |
| **B. Equivalent mutation** | No observable semantic change | Document equivalence. |
| **C. Non-consensus mutation** | Outside frozen Protocol V2 semantics | Exclude with justification. |

We never improve the mutation score by weakening assertions or excluding
meaningful mutations.

## Consensus-critical markers

We add `# CONSENSUS-CRITICAL` markers to the top of each consensus module and
next to particularly sensitive validators, with a short rule:

> Changes to this code require:
> - protocol compatibility review
> - frozen-vector review
> - regression tests
> - cross-language impact assessment (Rust verifier, if applicable)

We avoid littering every line; the marker is reserved for module boundaries
and high-stakes expressions.

## Deliverables

1. `docs/CONSENSUS_MUTATION_TEST_PLAN.md` (this file)
2. `docs/CONSENSUS_CHANGE_POLICY.md`
3. `# CONSENSUS-CRITICAL` markers in consensus modules
4. `docs/CONSENSUS_MUTATION_RESULTS.md`
5. Regression tests for any dangerous survivors found

## Exit criteria

- Plan is reviewed and committed on `phase7d-consensus-mutation-testing`.
- Mutation campaign executed.
- Results classified and documented.
- No consensus behavior changed merely to improve mutation scores.
