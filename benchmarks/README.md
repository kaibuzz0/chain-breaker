# Chain-Breaker Benchmarks

This directory contains reproducible benchmarks for the Chain-Breaker engine. Benchmarks are intentionally coarse at alpha; they establish baselines for future optimization rather than optimize prematurely.

## Running benchmarks

```bash
python -m benchmarks.run
```

Individual suites:

```bash
python -m benchmarks.run --suite hash
python -m benchmarks.run --suite block
python -m benchmarks.run --suite replay
python -m benchmarks.run --suite attest
python -m benchmarks.run --suite archive
python -m benchmarks.run --suite memory
```

## Suites

| Suite | Measures |
|-------|----------|
| hash | Header/block hashing throughput |
| block | Block mining and validation throughput |
| replay | Full ledger replay speed |
| attest | Attestation creation and verification throughput |
| archive | Archive hashing and verification throughput |
| memory | Peak memory usage during chain replay |

## Output

Results are written to `benchmarks/results/<suite>.json` and `benchmarks/results/latest.json`. Each result includes:

- `suite`
- `python_version`
- `platform`
- `iterations`
- `mean_seconds`
- `stddev_seconds`
- `throughput_per_second` (where applicable)
- `peak_memory_mb`
