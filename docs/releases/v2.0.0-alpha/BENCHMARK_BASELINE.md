# Benchmark Baseline — v2.0.0-alpha

## Determinism baseline

- Canonical block hashes are reproducible across Python 3.10/3.11/3.12.
- Genesis registry root is identical across all CI runs.

## Performance baseline (not yet instrumented)

No formal benchmarks are included in the alpha. The project relies on deterministic test vectors and CI timing as a coarse signal.

## Future work

- Add micro-benchmarks for hashing, serialization, and proof-of-work difficulty.
- Add end-to-end ingestion benchmarks for block validation throughput.
- Add memory-usage baselines for chain replay.
