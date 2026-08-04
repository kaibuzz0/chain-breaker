# Chain-Breaker Protocol v2  Independent Read-Only Gap Review

**Branch:** `registry-governance-hardening`  
**HEAD:** `6cb725accec8d504a8b8e53ecbeefe1cb3857d4f`  
**Review date:** 2026-08-02  
**Mode:** read-only; no code changes committed

---

## Review scope

Documents reviewed:

* `docs/PROTOCOL.md`
* `docs/HEADER_V2_DESIGN.md`
* `docs/CONSENSUS_INVARIANTS.md`
* `FINAL_ADVERSARIAL_REVIEW.md`

Code reviewed:

* `chainbreaker/block.py`
* `chainbreaker/chain.py`
* `chainbreaker/codec.py`
* `chainbreaker/crypto.py`
* `chainbreaker/governance.py`
* `chainbreaker/registry_state.py`
* `chainbreaker/witness.py`

---

## 1. Protocol vs implementation consistency

### Finding 1.1: Genesis registry-root semantics changed during implementation

**Severity:** Medium (documentation mismatch, now internally consistent)

**Location:** `docs/HEADER_V2_DESIGN.md` and `docs/CONSENSUS_INVARIANTS.md`

**Evidence:**

`HEADER_V2_DESIGN.md` originally stated:

```text
Genesis block (H=0) commits to:
    header.registry_root = registry_root(RegistryState.empty())
```

`CONSENSUS_INVARIANTS.md` (Model B) and the implementation agree that:

```text
genesis.registry_root == registry_root(RegistryState.genesis(governance_keys, threshold))
```

`registry_state.py:179` computes:

```python
return cls(
    records=(),
    governance_version=GOVERNANCE_SCHEMA_VERSION,
    network_id=NETWORK_ID,
    governance_keys=tuple(sorted_keys),
    threshold=threshold,
)
```

`RegistryState.empty()` is not used for the genesis block in the current code.

**Implication:** The design document still contains the old Model A sentence.
The implementation and the invariants document now use Model B. This is only a
stale-doc issue, but it could confuse an independent implementer.

**Recommended action:** Update `docs/HEADER_V2_DESIGN.md` to remove the
`RegistryState.empty()` genesis sentence and align with `CONSENSUS_INVARIANTS.md`
and `registry_state.py`.

---

### Finding 1.2: Type marker discrepancy in design documents

**Severity:** Low

**Location:** `docs/HEADER_V2_DESIGN.md`, `docs/HEADER_V2_TEST_VECTORS.md`

**Evidence:**

The implementation uses:

```python
TYPE_HEADER = 0x02
```

in `chainbreaker/codec.py:70`. The design documents originally said `0x01` and
were later updated, but the source text still has an offset table that says
"0x01 (BinaryCodec.TYPE_HEADER)". The implementation, genesis header bytes, and
tests use `0x02`.

**Implication:** Minor documentation inconsistency; does not affect consensus.

**Recommended action:** Verify all design docs say `0x02` consistently.

---

### Finding 1.3: `CONSENSUS_INVARIANTS.md` chain-work formula differs from code

**Severity:** Medium (possible subtle fork-choice mismatch)

**Evidence:**

Invariant 7 states:

```text
chain_work(chain) = SUM over blocks in chain:  MAX_TARGET / (block.target + 1)
```

`chainbreaker/crypto.py:186-190` implements:

```python
def work_for_target_v2(target: int) -> int:
    if target <= 0:
        raise ValueError("target must be positive")
    return MAX_TARGET // target
```

and `chain.py:395-403` sums this value.

The protocol spec `PROTOCOL.md` Section 5.2 says work is based on PoW validity,
but does not define chain work explicitly. The actual formula in code is
`floor(MAX_TARGET / target)`, not `MAX_TARGET / (target + 1)`.

**Implication:** The invariant document does not match the code. If two
implementers use the invariant doc literally, they would compute a different
chain work. Because fork choice is not yet used for consensus enforcement in
code (only `chain_work()` is exposed), the immediate risk is low, but the
spec is wrong.

**Recommended action:** Update `CONSENSUS_INVARIANTS.md` to use
`floor(MAX_TARGET / target)` and add a test vector for chain work.

---

## 2. Consensus path audit

### Finding 2.1: `add_block_v2` does not validate `header.version`

**Severity:** High (header-version bypass)

**Location:** `chainbreaker/chain.py:298-336`

**Evidence:**

`add_block_v2` checks:

* `block.header.prev_hash`
* `block.header.target`
* `isinstance(block.header, BlockHeaderV2)`
* `registry_root` against `_state_at`
* calls `block.verify(...)`

`BlockV2.verify` (`block.py:342-377`) checks target bounds, Merkle root, PoW,
`timestamp > 0`, future timestamp, median past, and transactions. Neither
`add_block_v2` nor `BlockV2.verify` asserts that `header.version == 2`.

Because `BlockV2` is typed to hold a `BlockHeaderV2`, the class alone
restricts the field set, but a `BlockHeaderV2` can be constructed with
`version=1` or `version=99` and still pass all current checks. The binary
codec enforces no version range either.

**Implication:** A malicious or misconstructed v2-shaped block with a non-2
version could be accepted into the chain. The block hash would differ from
what the protocol expects for version 2, but the ledger would still accept it
as long as PoW and other checks pass.

**Recommended action:** Add an explicit `header.version == PROTOCOL_VERSION`
check in `BlockV2.verify` and in `add_block_v2`. Add regression tests.

**Code change required:** Yes.

---

### Finding 2.2: `block_decode` version/type detection is heuristic

**Severity:** Medium

**Location:** `chainbreaker/chain.py:432-441`

**Evidence:**

```python
if len(data) >= 149 and data[0] == BinaryCodec.TYPE_HEADER and int.from_bytes(data[1:5], "little") == 2:
    header, offset = BinaryCodec.decode_header_v2(data)
```

A malformed 149-byte blob starting with `0x02` and version `2` will be parsed
as a v2 block header even if the rest is random. The decoder runs to
completion; PoW validation happens later. This is acceptable for storage, but
it means `block_decode` cannot be used as a consensus gate on its own.

**Implication:** Not a direct consensus failure because all later validation
checks PoW/Merkle, but the decoder does not enforce that the byte sequence is
a valid v2 header before returning a `BlockV2` object.

**Recommended action:** Ensure every `block_decode` result is passed through
`add_block_v2` / `BlockV2.verify` before acceptance. Document that `block_decode`
is a format decoder, not a consensus validator. This appears to already be
the case, but worth a code comment.

**Code change required:** No; documentation only.

---

### Finding 2.3: `validate_chain` uses `int(time.time())` for future-timestamp check

**Severity:** High (determinism violation)

**Location:** `chainbreaker/chain.py:367-368`

**Evidence:**

```python
if current.header.timestamp > int(time.time()) + 7200:
    return False
```

`validate_chain()` is supposed to be a deterministic replay of the chain. The
future-timestamp rule depends on the wall-clock time of the validating node.
Two nodes validating the same chain at different times could disagree if a
block timestamp is within 2 hours of one node's clock but past another node's
clock.

This directly violates `CONSENSUS_INVARIANTS.md` #1 (Determinism):

```text
The function f must not depend on: wall-clock time
```

**Implication:** A block that is valid today could become invalid in the
future, or vice versa, depending on node clocks. This is a consensus
divergence vector.

**Recommended action:** Remove the wall-clock-dependent future-timestamp check
from `validate_chain`, or make it optional and clearly outside the consensus
function. Use `reference_time` parameter consistently with a documented default
if needed. The `BlockV2.verify` signature already accepts `reference_time`;
`validate_chain` should pass a deterministic value (e.g., the chain tip's
timestamp or skip the check).

**Code change required:** Yes.

---

### Finding 2.4: `next_block_timestamp()` uses `int(time.time())`

**Severity:** Medium (mining determinism)

**Location:** `chainbreaker/chain.py:151-160`

**Evidence:**

```python
now = int(time.time())
return max(
    now,
    last_ts + 1,
    median + 1,
)
```

Mining uses wall-clock time to choose the next block timestamp. Different miners
with different clocks will choose different timestamps, producing different
block hashes and different nonces. This is normal for PoW systems and is not a
consensus failure by itself, but it means block production is not fully
deterministic. The protocol spec should state that mining is allowed to use
local wall-clock time.

**Implication:** Non-consensus-affecting for validity, but makes deterministic
test vectors for non-genesis mining impossible.

**Recommended action:** Document that mining timestamp selection is
miner-local and not part of the deterministic validation function. No code
change needed unless deterministic mining is a goal.

---

### Finding 2.5: `mine_block_v2` applies `validate_transaction` only when creating v1 blocks

**Severity:** Medium

**Location:** `chainbreaker/chain.py:235-265` vs `199-233`

**Evidence:**

`mine_block` (v1) calls:

```python
for tx in transactions:
    validate_transaction(tx)
```

`mine_block_v2` does not call `validate_transaction` before computing the
Merkle root or mining. It relies on `add_block_v2` rejecting invalid
transactions later. However, the Merkle root is computed over
`HashEngine.hash_object(tx)`, which will hash almost any dict shape. A
malformed governance transaction will still produce a block and be rejected at
admission, but a malformed non-governance transaction (e.g., with extra keys)
could be silently included.

**Implication:** `mine_block_v2` may produce blocks that fail admission due
to schema issues that should have been caught earlier. Not a consensus failure,
but a mining UX issue.

**Recommended action:** Add `validate_transaction(tx)` to `mine_block_v2`
before computing the Merkle root. Add regression test.

**Code change required:** Yes (minor).

---

### Finding 2.6: `add_block_v2` does not re-validate Merkle root independently

**Severity:** Medium

**Location:** `chainbreaker/chain.py:298-336`

**Evidence:**

`add_block_v2` relies on `block.verify(...)` to check the Merkle root. That is
acceptable, but the registry-root check and governance-transaction application
happen *before* `block.verify` is called. If `block.verify` later rejects the
block, the ledger has already accepted prev_hash/target/registry_root checks
but has not mutated state. This ordering is safe because state mutation
happens only after `block.verify` returns True.

**Implication:** Safe as implemented, but the ordering should be documented so
future edits do not move state mutation before PoW/structural checks.

**Recommended action:** Add a code comment in `add_block_v2` documenting the
intentional ordering: structural -> registry root -> PoW/Merkle -> apply state.
No code change.

---

### Finding 2.7: Governance context always uses genesis governance keys

**Severity:** High (future governance transition not implemented)

**Location:** `chainbreaker/chain.py:66` and `registry_state.py`

**Evidence:**

```python
self._governance_context = GovernanceContext(self.governance_keys, self.governance_threshold)
```

This context is fixed at ledger initialization and never changes. The
protocol v2 design says the genesis governance key set is fixed in the
registry state, but it does not preclude a future mechanism to rotate
governance keys. The current implementation cannot rotate governance keys
because `GovernanceContext` is static and the reducer validates curator
transactions against the *genesis* governance keys, not the current state's
`governance_keys`.

In `_apply_register`, `_apply_rotate`, `_apply_revoke`:

```python
context.verify_governance_signatures(body_without_witness, tx.governance_signatures)
```

The context comes from `self._governance_context` in `chain.py`, which is
built from the constructor arguments, not from the state at the current height.

**Implication:** The system enforces a permanently static governance set. This
matches the current "fixed genesis governance key set" requirement, but it
also means the `governance_keys` field in `RegistryState` is effectively a
commitment with no operational effect. If a future feature wants to rotate
governance keys, the entire signature validation path must change.

**Recommended action:** Document this limitation explicitly in
`docs/PROTOCOL.md` and `FINAL_ADVERSARIAL_REVIEW.md`. If the intent is truly
fixed governance forever, the state commitment is sufficient. If not, the design
must be extended before production.

**Code change required:** No for current scope; documentation required.

---

## 3. Determinism review

### Finding 3.1: `validate_chain` is non-deterministic due to wall-clock time

(See Finding 2.3)

---

### Finding 3.2: `target_to_hex` / `hex_to_target` use big-endian

**Severity:** Low (documentation note)

**Location:** `chainbreaker/crypto.py`

**Evidence:**

```python
def target_to_hex(target: int) -> str:
    return target.to_bytes(32, "big").hex()
```

`PROTOCOL.md` Section 5 says the target field is "uint256 little-endian" in the
header layout, but the code stores the target as a 32-byte big-endian hex
string and the codec writes it raw with `encode_hash(header["target"])`. The
codec does not interpret target byte order; it treats the 32-byte field as an
opaque hash-like blob.

The comparison `int(header_hash, 16) <= target` interprets the target as a
Python integer, which is endian-independent. So the actual consensus behavior is
consistent.

**Implication:** The spec wording "uint256 little-endian" for the target is
misleading because the target is not decoded as a little-endian integer; it is
treated as a raw 32-byte value. The genesis target hex
`0000ffff00000000...` is the same in both interpretations for this value, but
not for all values.

**Recommended action:** Clarify the spec: the target is a 32-byte raw field
whose hex string is stored big-endian for display, but consensus compares the
target as an integer via `int.from_bytes(..., "big")` or via the raw bytes.
Make the byte order unambiguous.

---

### Finding 3.3: Registry-state serialization sorts records by UTF-8 bytes

**Severity:** Low (interoperability)

**Location:** `chainbreaker/registry_state.py:214`

**Evidence:**

```python
sorted_records = sorted(state.records, key=lambda r: r.curator_id.encode("utf-8"))
```

This is deterministic across Python versions, but an independent implementer
must know the exact sort order (UTF-8 byte lexicographic). The protocol spec
should state this explicitly.

**Recommended action:** Add the record sorting rule to `docs/PROTOCOL.md`
Section 10 (registry state serialization).

---

## 4. Governance review

### Finding 4.1: Signature verification swallows all crypto exceptions silently

**Severity:** Medium

**Location:** `chainbreaker/governance.py:356-362`

**Evidence:**

```python
try:
    pk = decode_public_key(self.public_keys_hex[sig.key_index])
    if verify(pk, message, sig.signature_hex):
        valid += 1
except (ValueError, TypeError, KeyError):
    continue
```

A malformed public key in the genesis governance set (or a signature that
triggers a bug in `verify`) is silently treated as an invalid signature. This
is safe because it just reduces the valid signature count, but it means a node
can never surface *why* a signature failed. More importantly, if the genesis
governance keys contain an invalid Ed25519 public key, the node will simply
never count signatures from that index, potentially making threshold
unreachable.

**Implication:** The genesis governance keys are validated in
`GovernanceContext.__init__` by `decode_public_key`, so an invalid key will
fail at ledger creation. Therefore this silent catch is only relevant for
runtime edge cases. Acceptable.

**Recommended action:** No code change. The constructor validation is
sufficient.

---

### Finding 4.2: `GovernanceContext` accepts up to 16 keys but `RegistryState.genesis` has no limit

**Severity:** Low

**Location:** `chainbreaker/governance.py:313` vs `registry_state.py:152-181`

**Evidence:**

`GovernanceContext` limits the key list to 1..16. `RegistryState.genesis`
checks only that the list is non-empty and that the threshold is valid. It
does not enforce the 16-key limit.

**Implication:** If someone constructs a `RegistryState` directly with more than
16 keys and a matching `GovernanceContext` with fewer keys, the state root will
commit to the full set, but signatures will only be checked against the
context's subset. In the current code path both are derived from the same
constructor arguments, so they match.

**Recommended action:** Add the 16-key limit to `RegistryState.genesis` for
consistency, or remove the limit from `GovernanceContext`. Minor hardening.

**Code change required:** Optional.

---

### Finding 4.3: Duplicate governance signatures do not fail fast

**Severity:** Low

**Location:** `chainbreaker/governance.py:346-355`

**Evidence:**

Duplicate `key_index` values are detected and rejected. Good. However, the
check counts only valid signatures. Two signatures from the same key with
different signature values would be caught by the `used_indices` set.

**Implication:** No issue found.

---

### Finding 4.4: Activation-height rule is enforced

**Severity:** None (positive finding)

**Location:** `chainbreaker/registry_state.py:320, 384, 433`

**Evidence:**

```python
if tx.activation_height <= block_height:
    raise RegistryError("activation_height must be greater than block_height")
```

The rule is enforced for register, rotate, and revoke. This matches
`docs/ACTIVATION_HEIGHT_CONSISTENCY.md`.

---

### Finding 4.5: Replay resistance via `previous_registry_root`

**Severity:** None (positive finding)

**Location:** `chainbreaker/registry_state.py:322, 386, 435`

**Evidence:**

Each governance transaction carries `previous_registry_root` and the reducer
rejects it if it does not match the current state root. This prevents replay
against a different state.

---

## 5. Cryptography review

### Finding 5.1: Governance and attestation messages have good domain separation

**Severity:** None (positive finding)

**Location:** `chainbreaker/governance.py:340-345` and `witness.py:177-191`

**Evidence:**

Governance message:

```python
{
    "network_id": NETWORK_ID,
    "version": PROTOCOL_VERSION,
    "type": "registry",
    "body_hash": HashEngine.hash_object_hex(body),
}
```

Attestation v2 message:

```python
{
    "network_id": NETWORK_ID,
    "version": 2,
    "type": "attestation",
    "body_hash": body_hash,
    "curator_id": curator_id,
    "block_height": block_height,
}
```

Different `type` values, different versions, and the attestation binds the
block height. Domain separation is adequate.

---

### Finding 5.2: Transaction ID includes governance signatures

**Severity:** Medium

**Location:** `chainbreaker/chain.py:108-109` and `registry_state.py:258-264`

**Evidence:**

```python
txid = HashEngine.hash_object_hex(parsed.to_dict())
```

`parsed.to_dict()` includes `governance_signatures`. Therefore the txid changes
if the signature ordering changes. `GovernanceContext` does not enforce a
canonical signature ordering; it just iterates the list provided. Two
transactions with the same body but different signature order will have
different txids.

**Implication:** The `registration_txid` in `CuratorRecord` depends on
signature order. This is deterministic only if signers agree on ordering. The
current helper `make_governance_signature` signs in key-index order, but a
malformed or adversarial transaction could reorder signatures and still pass
threshold, producing a different state root.

**Recommended action:** Consider canonicalizing the signature list before
hashing (e.g., sort by key_index) in `_txid_from_body`, or document that
transaction IDs are not consensus-critical. The registry root *is*
consensus-critical, and it currently depends on signature order through the
`registration_txid` field. This is a potential determinism hazard.

**Code change required:** Yes (sort signatures by key_index before hashing).

---

### Finding 5.3: Ed25519 public key "0x00..." placeholders are accepted as valid keys

**Severity:** High (genesis key material)

**Location:** `chainbreaker/block.py:30-34`

**Evidence:**

```python
GENESIS_GOVERNANCE_KEYS = [
    "0000000000000000000000000000000000000000000000000000000000000000",
    ...
]
```

The comment says these are placeholder keys and must be replaced by a
production ceremony. However, the code currently uses them as the default
governance set. `decode_public_key` will accept these bytes, but all-zero and
all-one Ed25519 public keys are not valid curve points. Signing/verification
with these keys will fail or be undefined. The tests use real generated keys
via `Ledger(governance_keys=...)`.

**Implication:** This is a known placeholder, not a hidden bug. It must be
documented as a pre-launch checklist item.

**Recommended action:** Keep the comment, add a `WARNING` in
`FINAL_ADVERSARIAL_REVIEW.md` that the default genesis keys are insecure
placeholders and must be replaced before any real network.

---

## 6. Remaining risks

### Risk 6.1: Reorganization engine is not implemented

Confirmed in `FINAL_ADVERSARIAL_REVIEW.md`. `chain.py` has no rollback logic
beyond reconstructing state from a different chain list. This is acceptable for
the current milestone.

### Risk 6.2: P2P/network layer absent

Confirmed. No networking code reviewed.

### Risk 6.3: Formal verification absent

Confirmed.

### Risk 6.4: No independent cryptographic audit

Confirmed.

### Risk 6.5: V1/V2 boundary in `Ledger.from_dict` is heuristic

**Severity:** Medium

**Location:** `chainbreaker/chain.py:417`

**Evidence:**

```python
chain = [Block.from_dict(b) if "registry_root" not in b["header"] else BlockV2.from_dict(b) for b in data["chain"]]
```

This decides v1 vs v2 based on the presence of a string key in the JSON header.
An attacker could add or remove the key to force the wrong block class. JSON
block dicts are not a consensus format; this is a serialization convenience.

**Implication:** As long as `Ledger.from_dict` is only used for trusted local
storage/tests, this is fine. It must never be used for network consensus input.

**Recommended action:** Document that `Ledger.from_dict` is not a consensus
input path and that network consensus must use `block_decode` + `add_block_v2`.

---

## 7. Summary table

| # | Finding | Severity | Component | Code change |
|---|---------|----------|-----------|-------------|
| 1.1 | Genesis root Model A still in `HEADER_V2_DESIGN.md` | Low-Medium | docs | No |
| 1.2 | Type marker wording `0x01` vs `0x02` | Low | docs | No |
| 1.3 | Chain-work formula mismatch | Medium | `CONSENSUS_INVARIANTS.md` | No |
| 2.1 | `header.version` not enforced | **High** | `chain.py`, `block.py` | **Yes** |
| 2.2 | `block_decode` heuristic | Medium | `chain.py` | No |
| 2.3 | `validate_chain` uses wall-clock time | **High** | `chain.py` | **Yes** |
| 2.4 | Mining timestamp uses wall-clock | Medium | `chain.py` | No* |
| 2.5 | `mine_block_v2` skips `validate_transaction` | Medium | `chain.py` | Optional |
| 2.7 | Governance context is static forever | High (design) | `chain.py`, `registry_state.py` | No* |
| 3.2 | Target byte-order spec ambiguity | Low | `PROTOCOL.md` | No |
| 3.3 | Record sort order not in spec | Low | `PROTOCOL.md` | No |
| 4.2 | Key-count limit inconsistency | Low | `governance.py`, `registry_state.py` | Optional |
| 5.2 | txid depends on signature order | **Medium** | `registry_state.py`, `chain.py` | **Yes** |
| 5.3 | Placeholder genesis keys | High (operational) | `block.py` | No* |
| 6.5 | `Ledger.from_dict` heuristic | Medium | `chain.py` | No |

*Code change not required for current milestone, but documentation required.

---

## 8. Recommended actions before PR

1. **Fix `header.version` enforcement** and add regression tests.
2. **Remove or parameterize wall-clock time in `validate_chain`** to restore
deterministic replay.
3. **Canonicalize governance signature order** in transaction IDs.
4. **Update `CONSENSUS_INVARIANTS.md`** chain-work formula.
5. **Update `HEADER_V2_DESIGN.md`** genesis-root and type-marker wording.
6. **Document remaining static-governance and placeholder-key risks** in
`FINAL_ADVERSARIAL_REVIEW.md`.
7. Re-run the full verification gate suite after any code change.

---

## 9. Conclusion

The consensus core is substantially hardened and the adversarial test
coverage is strong. The findings above are mostly documentation gaps and two
to three code issues that should be fixed before human review. The most
important code changes are:

* deterministic `validate_chain` (remove wall-clock dependency)
* enforce `header.version == 2`
* canonical signature ordering in txids

No findings indicate an immediate consensus failure in the tested code paths,
but the `validate_chain` wall-clock dependency is a direct violation of the
stated determinism invariant and should be treated as a high-priority fix.
