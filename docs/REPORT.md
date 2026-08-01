# Chain-Breaker Consensus-Correctness Phase Report

## Starting point

- Repository: https://github.com/kaibuzz0/chain-breaker
- Starting commit: `24e3724480c5f9748b073c4c5453eddb683818fb`
- Local working tree: `D:\tmp\chain-breaker-rewrite`
- Environment limitation: no `git` or `gh` CLI available in this sandbox; `ssh.exe` exists but no configured key. Pushing was not performed.

## Defects fixed

1. **`chainbreaker/codec.py` imported `HashEngine` without importing it.**
   - Added `from .crypto import HashEngine` and hardened `decode_transaction` to catch `UnicodeDecodeError`/`json.JSONDecodeError`.
   - Added codec round-trip and malformed-input tests.

2. **Difficulty model used bit-count linear scaling.**
   - Replaced with a full 256-bit integer target.
   - PoW check is now `int(block_hash, 16) <= target`.
   - Added `target_to_hex`, `hex_to_target`, `target_to_difficulty`, `difficulty_to_target`, `work_for_target`, and accumulated chain-work tracking.

3. **Retarget boundaries were inconsistent.**
   - `Ledger.expected_target_at(height)` is now the single pure function used by mining, admission, and validation.
   - Difficulty changes only at `DIFFICULTY_RETARGET_INTERVAL` boundaries.
   - Added invariant tests that `add_block`-accepted blocks survive `validate_chain()` across multiple retarget periods.

4. **Block hash was effectively triple SHA-256.**
   - Corrected to documented double SHA-256 via `HashEngine.hash_double_hex()`.
   - Added fixed test vectors.

5. **Genesis was mined on every call.**
   - Hard-coded canonical genesis constants: network ID, protocol version, timestamp, previous hash, Merkle root, target, nonce, serialized header, and final block hash.
   - `create_genesis_block()` returns the canonical block without mining.
   - `Block.verify(..., allow_genesis=True)` checks the genesis hash and constants.

6. **Witness freshness conflated with historical validity.**
   - `verify_attestation()` is now purely cryptographic + registry-state validity; it never rejects an old signature.
   - `is_fresh()` remains available only for initial submission/mempool checks.

7. **Ledger did not enforce transaction witnesses.**
   - `Ledger.add_block()` now validates every transaction schema and witnesses via `verify_transaction_witnesses()`.
   - Blocks with unsupported types, missing fields, malformed hashes, unknown curators, invalid signatures, duplicate witnesses, or insufficient attestations are rejected.

8. **No explicit scripture/archive manifest schema.**
   - Defined `chainbreaker-manifest-v1` with required and optional fields.
   - Curators sign the complete canonical manifest bytes.

9. **Curator registry was arbitrary and mutable.**
   - Added `Registry` with deterministic ID-to-key binding, activation height, revocation height, key rotation, and duplicate-key/duplicate-ID rejection.
   - Documented that registry state must eventually be committed to the ledger (current code parses registry transactions but does not yet derive the full registry from chain history).

10. **Ed25519 parsing could raise on malformed input.**
    - `verify_attestation()` now catches `ValueError`, `KeyError`, and `TypeError` and returns `False`.
    - Signature and public-key lengths are checked before verification.

11. **Canonical JSON allowed floats and other unsafe values.**
    - `validate_transaction()` and `validate_scripture_body()` explicitly reject floats, NaN, Infinity, unsupported types, excessive nesting, and unbounded values.
    - One canonical binary representation is used for hashing and signing; JSON is for display only.

## Verification results

| Gate | Command | Result |
|------|---------|--------|
| Tests | `pytest -v` | 62 passed |
| Coverage | `pytest --cov=chainbreaker --cov-report=term-missing` | 80% total |
| Lint | `ruff check chainbreaker tests` | All checks passed |
| Type check | `mypy chainbreaker` | Success, no issues |
| Build | `python -m build` | Successfully built `chainbreaker-0.2.0` |
| Vulnerability audit | `pip-audit -r requirements.txt` | No known vulnerabilities |
| Security scan | `bandit -r chainbreaker` | No issues identified |
| Secret scan | manual regex scan | No obvious secrets in source |
| Clean tree | visual inspection | No `__pycache__`, `.coverage`, build, dist, or cache dirs |

Coverage detail (after cleanup):
- `chainbreaker/__init__.py`: 100%
- `chainbreaker/archive.py`: 93%
- `chainbreaker/block.py`: 94%
- `chainbreaker/chain.py`: 86%
- `chainbreaker/cli.py`: 62% (smoke-tested)
- `chainbreaker/codec.py`: 70%
- `chainbreaker/crypto.py`: 91%
- `chainbreaker/witness.py`: 77%

Main uncovered paths: CLI `mine`/`archive add` interactive commands, some `CodecError` branches, registry rotation/revoke governance transactions, and archive metadata-only paths.

## Files changed

All files under `chainbreaker/` and `tests/` were rewritten or heavily modified:
- `chainbreaker/crypto.py`
- `chainbreaker/codec.py`
- `chainbreaker/block.py`
- `chainbreaker/chain.py`
- `chainbreaker/witness.py`
- `chainbreaker/archive.py`
- `chainbreaker/cli.py`
- `chainbreaker/__init__.py`
- `chainbreaker/__main__.py`
- `tests/test_crypto.py`
- `tests/test_block.py`
- `tests/test_codec.py`
- `tests/test_chain.py`
- `tests/test_witness.py`
- `tests/test_archive.py`
- `tests/test_adversarial.py` (new)
- `tests/test_cli.py` (new)
- `docs/PROTOCOL.md` (new)
- `README.md`
- `.github/workflows/ci.yml`
- `pyproject.toml`
- `requirements.txt`
- `.gitignore`

## Protocol specification (concise)

### Transaction encoding
- One canonical binary encoding in `chainbreaker/codec.py`.
- Header: version varint, type length + UTF-8 type, body length + UTF-8 JSON body, witnesses length + UTF-8 JSON witnesses.
- No floats, NaN, Infinity, unbounded nesting, or unsupported types allowed.
- Transaction ID and signature pre-image use the binary-encoded transaction bytes or the canonical JSON body hash.

### Block hashing
- Canonical header serialization: version, prev_hash (32 bytes), merkle_root (32 bytes), timestamp (uint64 LE), target (32 bytes BE), nonce (uint64 LE).
- Header hash = `SHA256(SHA256(header_bytes))` (double SHA-256).
- Block hash is recomputed on deserialization; stored `hash` field is ignored.

### Target calculation
- 256-bit unsigned integer target.
- `MAX_TARGET` and `MIN_TARGET` bounds.
- Work for a target = `MAX_TARGET / target`.
- Difficulty changes only at `DIFFICULTY_RETARGET_INTERVAL` (10 blocks) using accumulated work.
- Retarget formula: `new_target = clamp(old_target * actual_time / expected_time, MIN_TARGET, MAX_TARGET)`.

### Genesis
- Network ID: `chainbreaker-scripture-v1`
- Protocol version: 1
- Timestamp: `1785542491`
- Previous hash: `0...0` (64 hex zeroes)
- Merkle root: `0...0`
- Target: `MAX_TARGET`
- Nonce: `116224`
- Block hash: `00001ec5b63d845f0afa2e499817c34a7e0de2b1c53675171645f60f36ea927c`

### Witnesses
- Attestation pre-image binds network ID, version, body hash, curator ID, and timestamp.
- Curator IDs are bound to Ed25519 public keys in a registry with activation/revocation heights.
- Historical attestations do not expire.
- Freshness check (`is_fresh`) is for submission only.

### Registry state
- Each curator record: `curator_id`, `public_key_hex`, `activation_height`, `revocation_height` (optional), `previous_key_hex` (optional).
- Duplicate IDs and duplicate witnesses are rejected.
- Key rotation creates a new record with the old key recorded as `previous_key_hex`.

## Unresolved risks

- CLI `mine` uses a placeholder signer identity (`alpha`) and does not enforce on-chain registry governance yet.
- Registry transactions are parsed but not automatically committed into a deterministic ledger-derived registry state.
- No P2P network layer; consensus rules are local-only.
- No checkpointing or long-range-attack protection beyond genesis and chain work.
- Canonical JSON is Python-specific; a cross-language binary manifest standard is deferred.
- `codec.py` coverage is 70%; some malformed-input branches are not yet exercised.

## Intentionally deferred features

- P2P networking
- Wallets and tokenomics
- Encrypted private vault
- Full cross-language canonical format
- On-chain registry governance state machine
- External cryptographic review

## Commit/push status

No commit was made in this environment because `git` and `gh` are not available. A clean local tree is ready at `D:\tmp\chain-breaker-rewrite`. Safe commands to commit and push from a machine with git/GitHub CLI or SSH are provided separately.
