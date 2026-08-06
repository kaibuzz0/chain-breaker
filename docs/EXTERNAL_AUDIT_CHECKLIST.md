# External Audit Checklist — Chain-Breaker v2.0.0-alpha

This checklist is the basis for an independent review of the Chain-Breaker alpha. Reviewers should verify each item and record findings in a separate report.

## 1. Consensus determinism

- [ ] The same block header always produces the same hash across Python 3.10/3.11/3.12.
- [ ] The genesis block is deterministic given the same seed registry and timestamp.
- [ ] Difficulty target interpretation is identical on all platforms.
- [ ] CI produces identical canonical hashes for the same test vectors.

## 2. Serialization correctness

- [ ] Every Header v2 field has a fixed serialization order.
- [ ] Length prefixes are always 4 bytes big-endian unsigned.
- [ ] Decoding rejects extra bytes, missing bytes, and out-of-order fields.
- [ ] All integer fields use fixed-width big-endian encoding.

## 3. Cryptographic correctness

- [ ] Block hashes use SHA-256 of canonical header bytes.
- [ ] Curator signatures use secp256k1 over canonical action payloads.
- [ ] Public-key recovery/validation rejects invalid or malformed keys.
- [ ] Private keys are never logged, serialized, or transmitted by the CLI.

## 4. Replay protection

- [ ] Block height is included in attestation payloads.
- [ ] Registry replay from genesis yields the same root as stored in each block.
- [ ] A revoked curator cannot produce valid attestations after revocation.
- [ ] A rotated key cannot sign attestations for blocks before rotation unless allowed by policy.

## 5. Registry governance

- [ ] Only an active curator can register, rotate, or revoke another curator.
- [ ] `register` requires a valid public key and self-signature.
- [ ] `rotate` requires the old private key and the new public key.
- [ ] `revoke` permanently removes the curator from the active set.
- [ ] The registry root commitment in each block matches the reducer output.

## 6. Witness validation

- [ ] Attestations are accepted only from curators active at the claimed height.
- [ ] Invalid signatures are rejected with a clear error.
- [ ] Attestations for non-existent block heights are rejected.
- [ ] Duplicate attestations from the same curator for the same height are handled consistently.

## 7. CLI security

- [ ] Path traversal is rejected before any file access.
- [ ] Symlink reads and writes are rejected before any file access.
- [ ] Overwrites require explicit `--force`.
- [ ] Atomic writes prevent half-written state files.
- [ ] UTF-8 validation rejects malformed free-form input.
- [ ] Exit codes are consistent and documented.

## 8. Archive integrity

- [ ] Archive files are append-only after finalization.
- [ ] Corrupted archive bytes are detected before dependent operations.
- [ ] Archive records include a hash linking them to the chain state.
- [ ] Empty archives and edge-case file sizes are handled safely.

## 9. Documentation completeness

- [ ] `docs/ARCHITECTURE.md` accurately reflects the module dependency graph.
- [ ] ADRs 001-003 match the implementation.
- [ ] `docs/THREAT_MODEL.md` covers all in-scope threats.
- [ ] `docs/OPERATOR_GUIDE.md` enables a non-developer to run a full workflow.
- [ ] `docs/DEVELOPER_GUIDE.md` enables a new contributor to build and test.

## 10. Build reproducibility

- [ ] `python -m build` succeeds on a clean checkout.
- [ ] The wheel installs and `hon --help` works in a fresh virtual environment.
- [ ] CI passes on Python 3.10, 3.11, and 3.12.
- [ ] No new unbounded dependencies or unpinned versions are introduced.

## Audit report template

For each finding, record:

| Field | Value |
|-------|-------|
| Item | Checklist number |
| Severity | critical / high / medium / low / info |
| Description | What was found |
| Reproduction | Exact command or test |
| Recommendation | Suggested fix or mitigation |
