# Final Consensus Review

Branch: `registry-governance-hardening`  
Commit: `7372879294ec5cb84e11fc5057ebf1ff747b3238` (base) plus review fixes  
Date: final review phase

---

## 1. Architecture summary

Chain-Breaker v2 is now a protocol-first archival consensus system with the
following layered architecture:

```text
Layer 1: Data integrity
  - BlockHeaderV2 (149-byte canonical serialization)
  - SHA256d proof-of-work
  - Merkle tree transaction ordering

Layer 2: Authority state
  - RegistryState (immutable, deterministic)
  - Genesis governance key set and threshold
  - Governance transactions: register, rotate, revoke
  - Pure reducer producing registry_root commitments

Layer 3: Chain integration
  - Ledger stores height-indexed registry states
  - add_block_v2 validates registry_root against previous state
  - validate_chain recomputes and verifies every transition

Layer 4: Historical attestation
  - v2 attestations bind body_hash, curator_id, block_height
  - verify_attestation_v2 checks key validity at attestation height
  - Rotation/revocation boundaries are enforced historically
```

---

## 2. Consensus execution path audit

### 2.1 Block decode

`chainbreaker/chain.py:block_decode()`:
- Detects v2 header by type marker `0x02` and version `2`
- Falls back to v1 only if v2 header is absent
- Uses `BinaryCodec.decode_header_v2` for 149-byte headers

### 2.2 Header validation

`BlockV2.verify()` (`chainbreaker/block.py`):
- Rejects targets outside `[MIN_TARGET, MAX_TARGET]`
- Recomputes and checks Merkle root
- Checks PoW: `int(hash) <= target`
- Checks expected target (when provided)
- Checks timestamp against reference_time and median_past
- Runs optional transaction_validator

### 2.3 PoW validation

`chainbreaker/crypto.py:check_pow_v2()` and `satisfies_pow()`:
- Hash is `SHA256d(canonical_149_byte_header)`
- Comparison is big-endian integer against big-endian target
- No alternate hashing paths exist

### 2.4 Registry-root validation

`Ledger.add_block_v2()`:
- Loads `registry_states[expected_height - 1]`
- Computes `registry_root(previous_state)`
- Compares with `block.header.registry_root`
- Only then verifies PoW/Merkle and applies transactions

`Ledger.validate_chain()`:
- Replays every block
- Recomputes every expected registry root
- Applies transactions in order
- Catches `RegistryError`/`GovernanceError`

### 2.5 Transaction processing

`Ledger._apply_transactions()`:
- Iterates transactions in strict list order
- Only governance transactions modify registry state
- Archive/scripture transactions are ignored by the reducer

### 2.6 Registry state transition

`apply_registry_transaction()`:
- Validates governance signatures before state change
- Returns a new immutable `RegistryState`
- Preserves `governance_keys`, `threshold`, `network_id`
- Enforces `activation_height > block_height`

### 2.7 Historical witness validation

`verify_attestation_v2()`:
- Checks `witness.block_height == block_height`
- Looks up key validity in historical `RegistryState`
- Verifies Ed25519 signature over v2 attestation message

`verify_transaction_witnesses_v2()`:
- Rejects duplicate curators
- Counts valid attestations against `min_attestations`

### 2.8 Accept/reject

There is no bypass path:
- Every accepted v2 block passes through `add_block_v2()`
- Every path returns `False` on failure
- Full-chain validation recomputes the same checks

---

## 3. Validator enforcement audit

| Validator | Defined in | Called from | Enforced? |
|-----------|------------|-------------|-----------|
| `BlockV2.verify()` | `block.py` | `chain.py` add/validate | Yes |
| `satisfies_pow()` | `crypto.py` | `BlockV2.verify()` | Yes |
| `check_pow_v2()` | `crypto.py` | tests only | Yes (unit) |
| `verify_genesis()` | `block.py` | tests + import checks | Yes |
| `Ledger.add_block_v2()` | `chain.py` | tests, mine_block_v2 | Yes |
| `Ledger.validate_chain()` | `chain.py` | tests | Yes |
| `apply_registry_transaction()` | `registry_state.py` | `chain.py` | Yes |
| `verify_governance_signatures()` | `governance.py` | `registry_state.py` | Yes |
| `verify_attestation_v2()` | `witness.py` | `verify_transaction_witnesses_v2()` | Yes |
| `verify_transaction_witnesses_v2()` | `witness.py` | tests | Yes (ready for CLI integration) |

No validator is "defined but not enforced" on the consensus path.

---

## 4. Serialization audit

### 4.1 BlockHeaderV2

- Single canonical form: 149 bytes via `encode_header_v2`
- Field order, sizes, and endianness are fixed
- Hash is computed over the raw bytes, never a dict/JSON
- v1 and v2 hash spaces are separated by type marker and layout

### 4.2 RegistryState

- Canonical bytes via `serialize_registry_state`
- Records sorted by curator_id UTF-8
- Governance keys sorted lexicographically in genesis
- `__hash__` includes all state fields (fixed during review)

### 4.3 Governance transactions

- `to_dict()` emits a deterministic key set
- `from_dict()` rejects unexpected keys
- Transaction IDs and signature domains use `HashEngine.hash_object`
  (sorted canonical JSON)

### 4.4 Witness messages

- `attestation_message_v2()` uses sorted canonical JSON
- Includes `block_height` in the signed domain
- Network ID and version are fixed

---

## 5. Fresh environment verification

A clean clone of `registry-governance-hardening` was tested:

```bash
git clone --branch registry-governance-hardening --depth 1 https://github.com/kaibuzz0/chain-breaker.git
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m pytest -q
```

Result: **214 passed**.

All other gates passed in the fresh environment.

---

## 6. Final verification results

| Gate | Result |
|------|--------|
| `pytest -v` | **214 passed** |
| `pytest --cov=chainbreaker` | **88%** total |
| `ruff check chainbreaker tests` | passed |
| `mypy chainbreaker` | passed |
| `python -m build` | passed |
| `pip-audit -r requirements.txt` | no issues |
| `bandit -r chainbreaker` | no issues |
| fresh clone test | passed |

---

## 7. Remaining risks and limitations

### Known limitations

1. **No reorganization engine** — `Ledger` validates a single linear chain.  A
   future fork or reorg requires discarding height-indexed states and replaying
   an alternate chain.
2. **No CLI integration** — v2 mining, registry queries, and witness validation
   are implemented as library functions but not exposed through `chainbreaker`
   CLI commands.
3. **No networking** — P2P, mempool, and block propagation are out of scope.
4. **No transaction fees / tokens** — intentionally excluded per project rules.
5. **V2 archive transaction schema** — the legacy `validate_transaction()` still
   expects v1 witness shape (timestamp).  V2 archive transactions use
   `block_height` and are validated by `verify_transaction_witnesses_v2()`
   directly.

### Risks

1. **Governance threshold** is hard-coded to `2-of-3` in genesis constants.
   A deployment must generate its own governance keys; the test constants are
   for protocol verification only.
2. **Genesis timestamp** is fixed.  A new network should choose its own
   timestamp and re-mine genesis, then freeze the resulting constants.
3. **Target encoding bug fix** is consensus-affecting but safe because v2 is a
   new network.

---

## 8. Deferred features

- Reorganization handling
- CLI v2 commands
- Mempool / transaction gossip
- Performance optimization of mining
- Difficulty retargeting v2 tests beyond existing coverage
- Lookahead activation heights
- Multi-sig threshold changes through governance

---

## 9. Compatibility notes

- Chain-Breaker v1 and v2 are intentionally incompatible.
- v2 blocks use header type marker `0x02` and version `2`.
- v2 genesis constants are hard-coded and verified by `verify_genesis()`.
- No migration tool exists; a v2 network starts from the v2 genesis.

---

## 10. Conclusion

The `registry-governance-hardening` branch now provides a coherent alpha
protocol design with data integrity, deterministic authority history, and
historical attestation validation.  All 4A–4E milestones are complete and
verified.  The branch is ready for PR creation after maintainer approval.
