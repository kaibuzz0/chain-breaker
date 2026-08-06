# Test Summary — v2.0.0-alpha

## Counts at freeze

- Total tests: ~756
- `chainbreaker/cli_v2.py` coverage: 82%
- Overall project coverage: 84%
- Skipped: 2 (Windows symlink privilege tests)

## CI matrix

| Python | Lint | Type check | Security scan | Test suite |
|--------|------|------------|---------------|------------|
| 3.10 | yes | yes | yes | pass |
| 3.11 | yes | yes | yes | pass |
| 3.12 | yes | yes | yes | pass |

## Test categories

- Unit tests for protocol serialization and hashing.
- Consensus invariants and registry-root validation.
- Replay, corruption, and adversarial/fuzz scenarios.
- CLI v2 end-to-end workflows including path traversal and symlink rejection.
- Wheel install and entry-point smoke test.
