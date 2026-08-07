# Documentation Truth Freeze — Chain-Breaker Protocol v2

## Status

Milestone: **Phase 6G — Documentation Truth Freeze**

Commit message: `freeze protocol v2 documentation against implementation`

Scope: audit every consensus/security claim in the v2 documentation against the
actual implementation at commit `57040bc03c2dc9efda260352949ce885db4f72fd`.

## Rule

Protocol v2 is frozen except for verified defects. No monetary layer, smart
contracts, networking, or Protocol v3 implementation may begin until this milestone
is merged and reviewed.

---

## Findings summary

| # | Inconsistency | File(s) | Classification | Corrected |
|---|---------------|---------|----------------|-----------|
| 1 | README claims registry transactions are "parsed but not committed" | `README.md` | CODE/SPEC | yes |
| 2 | README claims CLI mine uses placeholder signer and does not enforce registry governance | `README.md` | CODE/KNOWN LIMITATION | yes |
| 3 | Threat model assumes `secp256k1` signatures | `docs/THREAT_MODEL.md` | SPEC | yes |
| 4 | External audit checklist says block hashes use single SHA-256 and curator signatures use `secp256k1` | `docs/EXTERNAL_AUDIT_CHECKLIST.md` | SPEC | yes |
| 5 | Architecture doc says block hash is `SHA-256(canonical(header))` | `docs/ARCHITECTURE.md` | SPEC | yes |
| 6 | ADR 001 says block hash is `SHA-256(canonical(header_bytes))` and integer endianness is big-endian | `docs/adr/001-protocol-v2.md` | SPEC | yes |
| 7 | ADR 002 says `registry_root` commits to state *after* applying the block | `docs/adr/002-consensus-freeze.md` | SPEC | yes |
| 8 | Alpha status uses ambiguous "SHA-256 block hashing" | `docs/ALPHA_STATUS.md` | SPEC | yes |
| 9 | Header/genesis/PoW design docs still say "design-only; no implementation yet" | `docs/HEADER_V2_DESIGN.md`, `docs/GENESIS_V2_SPECIFICATION.md`, `docs/POW_V2_SPECIFICATION.md` | SPEC | yes |
| 10 | Operator and developer guides reference obsolete `hon` CLI and `chainbreaker/consensus.py` | `docs/OPERATOR_GUIDE.md`, `docs/DEVELOPER_GUIDE.md` | SPEC/KNOWN LIMITATION | yes |
| 11 | README tagline focuses on scripture rather than generalized archival provenance | `README.md` | SPEC | yes |

---

## Detailed findings

### 1. Registry transactions are committed to ledger state

**Stale claim:**

> Registry transactions are parsed but not committed into the ledger state machine.
> They can be injected into blocks, but the ledger does not automatically derive
> a deterministic registry from chain history.
>
> — `README.md` line 79

**Code evidence:**

- `chainbreaker/chain.py:116-124` — `Ledger._apply_transactions()` parses governance
  transactions and calls `apply_registry_transaction()` to produce a new
  `RegistryState`.
- `chainbreaker/chain.py:260-271` — `Ledger.mine_block_v2()` computes the registry root
  from the previous state and commits it in the new block header.
- `chainbreaker/chain.py:328-347` — `Ledger.add_block_v2()` validates the header
  `registry_root` against the previous state, then applies transactions to produce
  the next state.
- `chainbreaker/registry_state.py:272-290` — `apply_registry_transaction()` is the pure
  deterministic reducer for register/rotate/revoke actions.

**Test evidence:**

- `tests/test_registry_state.py` exercises register, rotate, revoke, replay,
  and `previous_registry_root` mismatch rejection.
- `tests/test_governance.py` validates governance signatures and reducer transitions.

**Correction:** README now describes the actual V2 implementation: registry
transactions are parsed, validated, and applied deterministically; each block
header commits to the previous registry state.

---

### 2. Signature algorithm is Ed25519, not secp256k1/ECDSA

**Stale claims:**

> Cannot break SHA-256, secp256k1, or the host OS without additional privileges.
>
> — `docs/THREAT_MODEL.md` line 20

> secp256k1 signatures remain unforgeable.
>
> — `docs/THREAT_MODEL.md` line 88

> Curator signatures use secp256k1 over canonical action payloads.
>
> — `docs/EXTERNAL_AUDIT_CHECKLIST.md` line 22

**Code evidence:**

- `chainbreaker/crypto.py:19-21` imports `Ed25519PrivateKey`, `Ed25519PublicKey`.
- `chainbreaker/crypto.py:189-193` decodes 32-byte Ed25519 public keys.
- `chainbreaker/crypto.py:204-208` decodes 32-byte Ed25519 private keys.
- `chainbreaker/crypto.py:220` verifies Ed25519 signatures.
- `chainbreaker/governance.py:395` imports `Ed25519PrivateKey`.
- `chainbreaker/governance.py:333-364` verifies governance signatures with Ed25519.
- `chainbreaker/witness.py:10` imports `Ed25519PrivateKey`, `Ed25519PublicKey`.
- `chainbreaker/witness.py:137-148`, `194-204` sign attestations with Ed25519.
- `chainbreaker/codec.py:453` enforces 64-char hex Ed25519 public keys.

**Specification:**

- Signature algorithm: Ed25519 (RFC 8032).
- Public key: 32 raw bytes, displayed as 64 lowercase hex characters.
- Private key: 32 raw bytes, displayed as 64 lowercase hex characters.
- Signature: 64 raw bytes, displayed as 128 lowercase hex characters.
- Signed preimage for attestations: canonical JSON hash of
  `{network_id, version, type, body_hash, curator_id, block_height}` (v2).
- Signed preimage for governance: canonical JSON hash of
  `{network_id, version, type, body_hash}`.
- Domain separation: `network_id`, `version`, and `type` fields are part of every
  signed message.

**Search result:** no `secp256k1` or `ECDSA` implementation exists in
`chainbreaker/` or `tests/`.

**Correction:** all documentation now states Ed25519 and defines the exact key,
signature, and preimage formats.

---

### 3. Block hashing is SHA-256d, not single SHA-256

**Ambiguous/stale claims:**

> Double-SHA-256 block hashing (not triple)
>
> — `README.md` line 12 (correct but colloquial)

> Block hashes use SHA-256 of canonical header bytes.
>
> — `docs/EXTERNAL_AUDIT_CHECKLIST.md` line 21

> A block hash is `SHA-256(canonical(header))`.
>
> — `docs/ARCHITECTURE.md` line 54

> The block hash is `SHA-256(canonical(header_bytes))`.
>
> — `docs/adr/001-protocol-v2.md` line 24

> SHA-256 block hashing.
>
> — `docs/ALPHA_STATUS.md` line 21

**Code evidence:**

- `chainbreaker/crypto.py:39-46` implements `double_sha256`.
- `chainbreaker/crypto.py:56-61` provides `hash_double` / `hash_double_hex`.
- `chainbreaker/block.py:69-74` documents header hashing as double-SHA256.
- `chainbreaker/block.py` (BlockHeaderV2.hash) produces the double-SHA256 digest.

**Test evidence:**

- `tests/test_block.py:29` — `test_header_hash_is_double_sha256`.
- `tests/test_genesis_v2.py:66` — genesis hash matches double SHA-256.
- `tests/test_crypto.py:20` — double-SHA256 vector.

**Specification:**

```text
SHA-256d(x) = SHA256(SHA256(x))

block_hash = SHA-256d(canonical_header_bytes)
```

The 32-byte digest is interpreted as a big-endian unsigned 256-bit integer for
the proof-of-work comparison.

**Correction:** every document now uses `SHA-256d` or the explicit
`SHA256(SHA256(...))` form for consensus-critical hashing. Colloquial
"Double-SHA-256" is retained in README only as a parenthetical.

---

### 4. Header integer endianness is little-endian, not big-endian

**Stale claim:**

> All integers are big-endian unsigned fixed-width.
>
> — `docs/adr/001-protocol-v2.md` line 20

> All integer fields use fixed-width big-endian encoding.
>
> — `docs/EXTERNAL_AUDIT_CHECKLIST.md` line 17

**Code evidence:**

- `chainbreaker/codec.py:33` — `ENDIAN = "<"` (little-endian).
- `chainbreaker/codec.py:211-218` encodes `version`, `timestamp`, `nonce` with
  little-endian struct formats.
- `chainbreaker/codec.py:244-269` decodes the same fields as little-endian.
- `docs/HEADER_V2_DESIGN.md` and `docs/POW_V2_SPECIFICATION.md` already state
  little-endian for version/timestamp/nonce.

**Specification:**

- Multi-byte integer fields in the v2 header are little-endian.
- Hash fields (`prev_hash`, `merkle_root`, `registry_root`, `target`) are 32 raw
  bytes; their hex display uses natural left-to-right byte order.
- Registry-state serialization (`chainbreaker/registry_state.py`) also uses
  little-endian varint/integer encoding.

**Correction:** ADR 001 and EXTERNAL_AUDIT_CHECKLIST now state little-endian
for integers. Big-endian remains only for PoW hash integer interpretation.

---

### 5. `registry_root` commits to state *before* the block

**Stale claim:**

> A block's `registry_root` is the SHA-256 of the canonical serialized registry state after applying that block's actions.
>
> — `docs/adr/002-consensus-freeze.md` line 38

**Code evidence:**

- `chainbreaker/chain.py:260-271` — mining computes `registry_root(previous_state)`
  where `previous_state = _state_at(height - 1)`.
- `chainbreaker/chain.py:328-332` — validation checks the header
  `registry_root` against `registry_root(previous_state)` for `expected_height - 1`.
- `chainbreaker/chain.py:345-347` — transactions are applied *after* the header
  check to produce `new_state`, which is then cached.

**Test evidence:**

- `tests/test_registry_state.py` tests `previous_registry_root` binding and
  replay semantics.
- `tests/test_governance.py` tests that governance transactions must reference
  the current state's root.

**Correct invariant (already in `docs/CONSENSUS_INVARIANTS.md:53-71`):**

```text
B[H].header.registry_root == registry_root(State(B[0..H-1]))

State_after(B[H]) = apply_registry_transactions(
                        State(B[0..H-1]),
                        governance_transactions(B[H]),
                        height=H
                    )
```

**Correction:** ADR 002 now matches the code and `CONSENSUS_INVARIANTS.md`.

---

### 6. Header/genesis/PoW docs were still marked "design-only"

**Stale status lines:**

> Status: **design-only milestone; no implementation yet**
>
> — `docs/HEADER_V2_DESIGN.md` line 5

> Status: **design-only; no implementation yet**
>
> — `docs/GENESIS_V2_SPECIFICATION.md` line 4

> Status: **design-only; no implementation changes**
>
> — `docs/POW_V2_SPECIFICATION.md` line 5

**Code evidence:**

- `chainbreaker/codec.py:196-221` implements `encode_header_v2` producing exactly
  149 bytes.
- `chainbreaker/block.py:162-...` implements `BlockHeaderV2` and genesis constants.
- `chainbreaker/chain.py` implements PoW validation with target decoding.
- `tests/test_header_v2.py`, `tests/test_genesis_v2.py`, `tests/test_pow_v2.py`
  exercise all three.

**Correction:** these documents now carry status **implemented and frozen at
v2.0.0-alpha**.

---

### 7. Operator and developer guides referenced obsolete CLI

**Stale references:**

- `docs/OPERATOR_GUIDE.md` uses the `hon` entry point and commands that do not
  exist in the current CLI (`hon chain init`, `hon block mine --difficulty-bits`,
  `hon archive add --chain`). The package entry point is `chainbreaker`, not `hon`.
- `docs/DEVELOPER_GUIDE.md` references `chainbreaker/consensus.py`, which does not
  exist (consensus validation lives in `chainbreaker/chain.py`, `chainbreaker/block.py`,
  and `chainbreaker/codec.py`). It also references `hon` commands.

**Correction:** operator and developer guides now use the current `chainbreaker v2`
CLI commands and the real module layout. A note marks the guides as accurate for
local v2 workflows; storage/networking commands remain future work.

---

### 8. README framing and status list

**Stale framing:**

- Tagline focused on "scripture" rather than the general archival-provenance
  mission.
- "What it proves today" mixed implemented features with obsolete caveats.
- Known risks included the false registry-state claim.

**Correction:** README now states:

> A deterministic blockchain protocol for preserving documents, provenance, and historical curator attestations.

It lists implemented features, in-development features, and explicit
not-production-ready status without exaggeration.

---

## Files corrected in this milestone

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/THREAT_MODEL.md`
- `docs/EXTERNAL_AUDIT_CHECKLIST.md`
- `docs/ALPHA_STATUS.md`
- `docs/OPERATOR_GUIDE.md`
- `docs/DEVELOPER_GUIDE.md`
- `docs/HEADER_V2_DESIGN.md`
- `docs/GENESIS_V2_SPECIFICATION.md`
- `docs/POW_V2_SPECIFICATION.md`
- `docs/adr/001-protocol-v2.md`
- `docs/adr/002-consensus-freeze.md`
- `docs/DOCUMENTATION_TRUTH_FREEZE.md` (this file)

## Unresolved ambiguities

1. **Governance-set rotation.** `CONSENSUS_INVARIANTS.md` and `ADR 002` freeze
   the initial genesis governance key set. A future Protocol v3 ADR must define
   how the governance set itself can be rotated deterministically.
2. **Transaction ID stability.** `registry_state.py` uses
   `HashEngine.hash_object_hex(body)` for the transaction ID, which is
   JSON-canonical. This is stable but Python-tooling-dependent; a future
   cross-language vector suite should include exact transaction-ID bytes.
3. **PoW comparison strictness.** `docs/POW_V2_SPECIFICATION.md` says `<= target`,
   and `BlockHeaderV2.verify` enforces `<=`. `docs/ARCHITECTURE.md` line 57
   historically said `< target`; this truth freeze corrects it to `<=`.
4. **Package version drift.** `docs/PROTOCOL.md` says package version `0.3.0`,
   but `pyproject.toml` and the wheel name use `0.2.0`. This is left as a
   documentation note because the protocol version (2) is frozen; the package
   version is release plumbing.
5. **Test counts.** `docs/ALPHA_STATUS.md` and `docs/releases/v2.0.0-alpha/TEST_SUMMARY.md`
   cite "756+ tests". The exact count fluctuates with new adversarial tests.
   The truth freeze keeps the approximate count but notes that the invariant
   is "deterministic CI passes on 3.10/3.11/3.12" rather than a hard number.

---

## Consensus-critical inventory (frozen at v2)

| Component | File | Frozen behavior |
|-----------|------|-----------------|
| Header V2 encoding | `chainbreaker/codec.py` | 149 bytes, type marker `0x02`, little-endian integers |
| Header V2 hash | `chainbreaker/block.py`, `chainbreaker/crypto.py` | `SHA-256d(canonical_header_bytes)` |
| Genesis constants | `chainbreaker/block.py` | hard-coded bytes, timestamp, target, governance keys |
| PoW target interpretation | `chainbreaker/block.py` | 256-bit integer, `hash_int <= target` |
| Registry root semantics | `chainbreaker/chain.py`, `chainbreaker/registry_state.py` | commits to state before the block |
| Governance reducer | `chainbreaker/registry_state.py` | register/rotate/revoke pure transitions |
| Historical attestation | `chainbreaker/witness.py` | Ed25519 over v2 message with block height |
| Canonical JSON hashing | `chainbreaker/crypto.py` | `sort_keys=True`, no whitespace, UTF-8 |
| Signature algorithm | `chainbreaker/crypto.py`, `chainbreaker/governance.py` | Ed25519 |

---

## Next milestones (in order)

1. **Phase 7A** — Durable storage architecture specification (WAL/journal,
   crash recovery, canonical binary storage, snapshots, archive layout,
   corruption detection). Do not implement code yet.
2. **Phase 7B** — Language-neutral golden test vectors.
3. **Phase 7C** — Cross-language verifier design (Rust reference).
4. **Phase 7D** — Consensus mutation testing.
5. **Phase 7E/F** — Storage implementation and crash/fault injection.
6. **Protocol V3 architecture** — only after V2 truth freeze, vectors, and
   verifier plan are stable.

No monetary settlement, smart contracts, tokenomics, or networking implementation
is permitted until the above sequence is complete.
