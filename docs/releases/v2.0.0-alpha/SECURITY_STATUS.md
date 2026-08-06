# Security Status — v2.0.0-alpha

## Automated checks (passing at alpha)

| Tool | Scope | Status |
|------|-------|--------|
| Ruff | lint/format/import order | green |
| mypy | static type checking | green |
| pip-audit | dependency vulnerability scan | green |
| Bandit | security anti-patterns | green |
| private-key scanning | accidental secret leakage | green |
| deterministic tests | replay/consensus stability | green |
| replay tests | state reproducibility | green |
| corruption tests | tamper detection | green |
| fuzz tests | adversarial input handling | green |

## Threat-model gaps

- Transport and network adversaries are not addressed (no networking yet).
- Storage confidentiality relies on host filesystem permissions.
- Curator key generation and custody are CLI-local; no HSM or secret-manager integration.

## Freeze declaration

Consensus rules, canonical serialization, and the v2 protocol grammar are frozen for alpha. Any change requires a version bump and migration path.
