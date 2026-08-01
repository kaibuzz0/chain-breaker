# Proof-of-Work v2 Implementation Checklist

Version: `chainbreaker-scripture-v2`  
Milestone: **4C — Mining and PoW integration**

---

## Serialization and target encoding

- [ ] Target is encoded as 32-byte big-endian unsigned integer.
- [ ] `target_to_hex` and `hex_to_target` use big-endian conversion.
- [ ] `encode_header_v2` produces exactly 149 bytes.
- [ ] Hash preimage is the 149-byte canonical header serialization.
- [ ] `BlockHeaderV2.hash()` returns the double-SHA256 hex digest of the canonical bytes.
- [ ] Hash digest is interpreted as big-endian 256-bit integer for comparison.

## PoW validity rule

- [ ] Valid PoW satisfies `int(SHA256d(header_bytes), 16) <= target`.
- [ ] No alternate hashing path exists.
- [ ] No implicit defaults; caller supplies header/target.
- [ ] `satisfies_pow` is updated to use the v2 canonical path.

## Mining loop

- [ ] Mining operates only on `BlockHeaderV2`.
- [ ] Only `nonce` varies during the search.
- [ ] Nonce increments deterministically starting from a supplied value.
- [ ] Nonce wraps modulo `2**64` on exhaustion.
- [ ] Changing any other header field restarts the search.
- [ ] Miner returns the found header and hash; does not silently mutate block state.
- [ ] Mining failure after `max_iterations` is explicit.

## Timestamp handling

- [ ] Timestamp is a 64-bit unsigned little-endian integer in the header.
- [ ] Timestamp is not allowed to vary during mining unless caller explicitly updates it.
- [ ] Timestamp changes reset the nonce search.

## Chain work

- [ ] Per-block work is `floor(MAX_TARGET / target)`.
- [ ] Total chain work is the integer sum of per-block work.
- [ ] Tests cover high target / low work, low target / high work.
- [ ] Tests cover minimum target, maximum target, invalid zero target, out-of-range target.
- [ ] Fork-choice rule uses greater chain work, with deterministic tie-breaker if needed.

## Genesis preservation

- [ ] Genesis is not re-mined at runtime.
- [ ] `verify_genesis()` still passes against hard-coded constants.
- [ ] Mining code refuses to operate on a genesis header.

## Compatibility

- [ ] v1 headers rejected by v2 PoW validator.
- [ ] v2 headers rejected by v1 PoW validator (existing behavior preserved).

## Fixed vectors and adversarial tests

- [ ] Valid PoW vector from `docs/POW_V2_SPECIFICATION.md` reproduced in tests.
- [ ] Invalid PoW vector with `nonce = 0` reproduced.
- [ ] Altered nonce test.
- [ ] Altered previous hash test.
- [ ] Altered merkle root test.
- [ ] Altered registry root test.
- [ ] Altered timestamp test.
- [ ] Altered target test.
- [ ] Truncated header test.
- [ ] Malformed target encoding test.
- [ ] Wrong byte order test.
- [ ] v1 header passed to v2 validator test.
- [ ] v2 header passed to v1 validator test.

## Verification gates

- [ ] `python -m pytest -v` passes.
- [ ] `python -m pytest --cov=chainbreaker` shows no coverage regression.
- [ ] `python -m ruff check chainbreaker tests` passes.
- [ ] `python -m mypy chainbreaker` passes.
- [ ] `python -m build` passes.
- [ ] `python -m pip_audit -r requirements.txt` passes.
- [ ] `python -m bandit -r chainbreaker` passes.

## Non-goals for this milestone

- [ ] Do not add registry-root chain validation.
- [ ] Do not add witness validation.
- [ ] Do not modify governance state or registry reducer.
- [ ] Do not modify CLI commands.
- [ ] Do not modify chain admission rules.
- [ ] Do not add fork/reorganization handling.
- [ ] Do not optimize mining performance.
