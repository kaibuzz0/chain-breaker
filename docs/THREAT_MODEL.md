# Chain-Breaker Threat Model

This document describes the threats the alpha release is designed to resist, the threats it explicitly does not address, and the assumptions that future work must preserve.

## Scope

- Protocol v2 consensus engine
- Registry governance reducer
- CLI v2 workflows
- Local archive storage

Out of scope: networking, distributed operation, storage backends, replication, production monitoring.

## Threat actors

### Actor A — Local operator

- Has shell access to the machine running `hon`.
- Can read and write files in the working directory.
- Cannot break SHA-256, Ed25519, or the host OS without additional privileges.

### Actor B — Malformed input supplier

- Can pass arbitrary file paths, keys, archives, and attestations to the CLI.
- Has no shell access beyond what the CLI allows.

### Actor C — Time/resource abuser

- Can trigger expensive operations such as mining or large archive replay.
- Cannot exhaust resources outside the CLI process without OS-level limits.

## Assets

| Asset | Value | Protection |
|-------|-------|------------|
| Curator private keys | Signature authority | Local filesystem permissions, symlink rejection, atomic writes |
| Chain state | Historical truth | Canonical hashing, integrity checks, deterministic replay |
| Archive files | Evidence base | Append-only finalization, hash verification |
| CLI input | Operational correctness | Path validation, UTF-8 checks, malformed-input tests |

## Threats addressed

1. **Accidental key exposure**
   - Private-key files are never logged.
   - CLI does not persist generated keys without explicit operator action.
   - Atomic writes prevent half-written key files.

2. **Local filesystem manipulation**
   - Symlink reads/writes are rejected before file access.
   - Path traversal is rejected before file access.
   - Overwrites require explicit `--force`.

3. **Malformed or adversarial input**
   - All free-form input is UTF-8 validated.
   - Canonical deserialization rejects extra or missing fields.
   - Fuzz tests cover header, block, archive, and attestation mutation.

4. **Replay attacks**
   - Block height is part of every attestation payload.
   - Registry state is replayed from genesis for validation.
   - Historical attestation set is checked against the active curator set at the relevant height.

5. **Consensus divergence**
   - Canonical serialization is deterministic.
   - Test vectors are shared across Python versions and CI platforms.

## Threats not addressed

1. **Network adversaries**
   - No peer protocol exists yet.
   - No transport encryption, DoS limits, or eclipse resistance.

2. **Multi-node collusion**
   - Only local curator signatures are validated.
   - No quorum or byzantine-fault-tolerant consensus exists yet.

3. **Host compromise**
   - If the operator's OS is compromised, private keys and chain state can be stolen or modified.

4. **Supply-chain attacks**
   - Dependency audits (pip-audit) are run but do not guarantee future dependency safety.

## Assumptions

1. The operator keeps curator private keys confidential.
2. The host OS provides filesystem permissions and randomness.
3. SHA-256 remains collision-resistant and preimage-resistant.
4. Ed25519 signatures remain unforgeable.
5. Python's standard library cryptographic primitives are correctly implemented.

## Future mitigations

| Phase | Mitigation |
|-------|------------|
| 7 | Pluggable storage backends with encrypted-at-rest option. |
| 8 | Transport encryption, peer authentication, rate limits. |
| 9 | Reorg engine with checkpointing and fork-choice rules. |
| 10 | Independent cryptographic and consensus review. |
