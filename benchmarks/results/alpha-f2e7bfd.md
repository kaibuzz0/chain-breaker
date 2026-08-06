# Benchmark Results — v2.0.0-alpha (ref: refs/heads/production-readiness-review)

**Commit:** `ref: refs/heads/production-readiness-review`  
**Timestamp:** 2026-08-06T01:27:34Z  
**Environment:** Windows-10-10.0.26100-SP0, Python 3.11.15, AMD64, 4 cores

## Important limitations

These numbers describe the alpha implementation **only** under local, single-node conditions:

- No networking
- No peer-to-peer synchronization
- No distributed storage
- No database backend
- No optimization pass
- All measurements are local in-memory or local-filesystem operations

Use them as a regression baseline, not as a production performance prediction.

## Summary table

| Suite | Iterations | Mean | Median | Min | Max | Stddev | Throughput |
|-------|------------|------|--------|-----|-----|--------|------------|
| sha256 | 100000 | 4.850e-06 | 2.900e-06 | 2.700e-06 | 0.034972 | 1.653e-04 | 20617464187.948975 /s |
| block_verify | 10000 | 7.207e-06 | 6.400e-06 | 6.100e-06 | 2.745e-04 | 7.677e-06 | 138759.765299 /s |
| block_mine | 100 | 0.467215 | 0.460705 | 0.391328 | 0.705246 | 0.059661 | 2.140343 /s |
| ledger_replay | 10 | 0.001494 | 0.001410 | 0.001242 | 0.002024 | 2.448e-04 | 134571.480235 /s |
| registry_replay | 10 | 0.058081 | 0.047763 | 0.030133 | 0.100623 | 0.028619 | 1721.733441 /s |
| attest create | 1000 | 6.071e-05 | 5.430e-05 | 4.940e-05 | 5.168e-04 | 2.499e-05 | 16298138.590308 ops/s |
| attest verify | 1000 | 6.490e-07 | 6.000e-07 | 3.000e-07 | 2.180e-05 | 8.142e-07 | - |
| archive_hash | 50 | 0.042647 | 0.042647 | 0.009263 | 0.076031 | 0.047212 | 23.448236 MB/s |
| memory | 1 | current 5.341e-05 MB | peak 0.001170 MB | - | - | - | - |
| startup | 50 | 2.273e-05 | 1.155e-05 | 1.100e-05 | 1.549e-04 | 3.154e-05 | 43986.979899 /s |

## Individual suites

### sha256

```json
{
  "mean": 4.850257000007332e-06,
  "median": 2.9000002541579306e-06,
  "min": 2.6999996407539584e-06,
  "max": 0.03497209999932238,
  "stddev": 0.00016533785901091453,
  "iterations": 100000,
  "throughput_per_second": 20617464187.948975,
  "suite": "sha256",
  "environment": {
    "os": "Windows-10-10.0.26100-SP0",
    "python_version": "3.11.15",
    "processor": "AMD64",
    "cpu_count": 4,
    "machine": "AMD64",
    "commit": "ref: refs/heads/production-readiness-review",
    "timestamp": "2026-08-06T01:27:34Z"
  },
  "unit": "seconds per hash"
}
```

### block_verify

```json
{
  "mean": 7.206699995822419e-06,
  "median": 6.400000529538374e-06,
  "min": 6.100000064179767e-06,
  "max": 0.0002745000001596054,
  "stddev": 7.676912051039355e-06,
  "iterations": 10000,
  "throughput_per_second": 138759.76529891352,
  "suite": "block_verify",
  "environment": {
    "os": "Windows-10-10.0.26100-SP0",
    "python_version": "3.11.15",
    "processor": "AMD64",
    "cpu_count": 4,
    "machine": "AMD64",
    "commit": "ref: refs/heads/production-readiness-review",
    "timestamp": "2026-08-06T01:27:34Z"
  },
  "unit": "seconds per verification"
}
```

### block_mine

```json
{
  "mean": 0.46721487800001343,
  "median": 0.46070529999997234,
  "min": 0.391327999999703,
  "max": 0.7052456999999777,
  "stddev": 0.05966140860359797,
  "iterations": 100,
  "throughput_per_second": 2.1403427996142947,
  "suite": "block_mine",
  "environment": {
    "os": "Windows-10-10.0.26100-SP0",
    "python_version": "3.11.15",
    "processor": "AMD64",
    "cpu_count": 4,
    "machine": "AMD64",
    "commit": "ref: refs/heads/production-readiness-review",
    "timestamp": "2026-08-06T01:28:21Z"
  },
  "unit": "seconds per mine",
  "note": "mining at genesis target"
}
```

### ledger_replay

```json
{
  "mean": 0.0014936299998225878,
  "median": 0.0014102499999353313,
  "min": 0.0012419999993653619,
  "max": 0.0020235000001775916,
  "stddev": 0.00024476117192244457,
  "iterations": 10,
  "chain_length": 201,
  "throughput_per_second": 134571.4802353157,
  "suite": "ledger_replay",
  "environment": {
    "os": "Windows-10-10.0.26100-SP0",
    "python_version": "3.11.15",
    "processor": "AMD64",
    "cpu_count": 4,
    "machine": "AMD64",
    "commit": "ref: refs/heads/production-readiness-review",
    "timestamp": "2026-08-06T01:30:02Z"
  },
  "unit": "seconds to replay full chain"
}
```

### registry_replay

```json
{
  "mean": 0.05808099999994738,
  "median": 0.047763449999820295,
  "min": 0.03013310000005731,
  "max": 0.10062310000012076,
  "stddev": 0.02861906863119145,
  "iterations": 10,
  "registry_steps": 100,
  "throughput_per_second": 1721.7334412301886,
  "suite": "registry_replay",
  "environment": {
    "os": "Windows-10-10.0.26100-SP0",
    "python_version": "3.11.15",
    "processor": "AMD64",
    "cpu_count": 4,
    "machine": "AMD64",
    "commit": "ref: refs/heads/production-readiness-review",
    "timestamp": "2026-08-06T01:30:03Z"
  },
  "unit": "seconds to replay registry transactions"
}
```

### attest

```json
{
  "suite": "attest",
  "iterations": 1000,
  "create": {
    "mean": 6.07077000049685e-05,
    "median": 5.429999964690069e-05,
    "min": 4.939999962516595e-05,
    "max": 0.0005167999997865991,
    "stddev": 2.4987277851557402e-05
  },
  "verify": {
    "mean": 6.489999923360301e-07,
    "median": 6.000000212225132e-07,
    "min": 2.999995558639057e-07,
    "max": 2.1799999558425043e-05,
    "stddev": 8.14150982386322e-07
  },
  "throughput_per_second": 16298138.590307677,
  "environment": {
    "os": "Windows-10-10.0.26100-SP0",
    "python_version": "3.11.15",
    "processor": "AMD64",
    "cpu_count": 4,
    "machine": "AMD64",
    "commit": "ref: refs/heads/production-readiness-review",
    "timestamp": "2026-08-06T01:30:04Z"
  },
  "unit": "seconds per create+verify pair"
}
```

### archive_hash

```json
{
  "mean": 0.04264713099999426,
  "median": 0.04264713099999426,
  "min": 0.00926337599999897,
  "max": 0.07603088599998956,
  "stddev": 0.04721175908393397,
  "iterations": 50,
  "sizes_mb": [
    1,
    10
  ],
  "throughput_per_second": 23.448236177953792,
  "suite": "archive_hash",
  "environment": {
    "os": "Windows-10-10.0.26100-SP0",
    "python_version": "3.11.15",
    "processor": "AMD64",
    "cpu_count": 4,
    "machine": "AMD64",
    "commit": "ref: refs/heads/production-readiness-review",
    "timestamp": "2026-08-06T01:30:08Z"
  },
  "unit": "seconds per MB archive hash"
}
```

### memory

```json
{
  "suite": "memory",
  "iterations": 1,
  "chain_length": 501,
  "current_memory_mb": 5.340576171875e-05,
  "peak_memory_mb": 0.0011701583862304688,
  "environment": {
    "os": "Windows-10-10.0.26100-SP0",
    "python_version": "3.11.15",
    "processor": "AMD64",
    "cpu_count": 4,
    "machine": "AMD64",
    "commit": "ref: refs/heads/production-readiness-review",
    "timestamp": "2026-08-06T01:34:44Z"
  },
  "unit": "MB"
}
```

### startup

```json
{
  "mean": 2.2733999976480846e-05,
  "median": 1.1550000181159703e-05,
  "min": 1.0999999176419806e-05,
  "max": 0.00015489999987039482,
  "stddev": 3.153630635507323e-05,
  "iterations": 50,
  "throughput_per_second": 43986.97989946936,
  "suite": "startup",
  "environment": {
    "os": "Windows-10-10.0.26100-SP0",
    "python_version": "3.11.15",
    "processor": "AMD64",
    "cpu_count": 4,
    "machine": "AMD64",
    "commit": "ref: refs/heads/production-readiness-review",
    "timestamp": "2026-08-06T01:34:44Z"
  },
  "unit": "seconds to create genesis block"
}
```

