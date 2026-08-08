# Phase 8K — Block Relay Implementation Report

## Status

**Block relay implementation complete.** The relay layer is a courier, not a
judge.

## Branch

- `phase8k-block-relay-implementation`
- Base: `phase8j-block-relay-architecture @ cb50358`

## Files added

| File | Purpose |
|------|---------|
| `chainbreaker/network/relay/__init__.py` | Public relay API |
| `chainbreaker/network/relay/errors.py` | Relay exceptions |
| `chainbreaker/network/relay/limits.py` | Relay limit policy |
| `chainbreaker/network/relay/inventory.py` | Inventory tracker |
| `chainbreaker/network/relay/cache.py` | Duplicate-seen cache |
| `chainbreaker/network/relay/engine.py` | Relay engine |
| `tests/network/relay/test_relay_cache.py` | Seen-cache tests |
| `tests/network/relay/test_inventory.py` | Inventory tracker tests |
| `tests/network/relay/test_relay_engine.py` | Relay engine tests |
| `tests/network/relay/test_relay_adversarial.py` | Adversarial tests |
| `docs/BLOCK_RELAY_SECURITY_REVIEW.md` | Security review |
| `docs/PHASE8K_BLOCK_RELAY_IMPLEMENTATION_REPORT.md` | This report |

## Architecture summary

```text
Local block validated
        |
        v
on_local_block()
        |
        v
INV_BLOCK to peers
        |
        v
handle_inv() -> GET_BLOCK
        |
        v
handle_block() -> ledger.validate()
        |
        v
StorageBackend.append_block()
        |
        v
Queue for further relay
```

## Test coverage

| Area | Tests |
|------|-------|
| Inventory tracker | 3 |
| Seen cache | 3 |
| Relay engine | 8 |
| Adversarial relay | 6 |
| **Total new** | **20** |
| **Network suite total** | **228** |

## Verification gates

| Gate | Result |
|------|--------|
| `ruff check chainbreaker tests` | ✅ |
| `mypy chainbreaker tests/network` | ✅ |
| `pytest tests/network/` (228) | ✅ |
| `python -m build --wheel` | ✅ |
| `bandit -r chainbreaker/network` | ✅ |
| `pip-audit -r requirements.txt` | ✅ |

## Boundary preservation

- Protocol V2 unchanged.
- No consensus file modified.
- No mempool, transaction relay, fee market, or mining communication.
- No registry/archive/governance coupling in relay logic.
- Storage commit uses existing `append_block()` path.

## Known limitations / future work

- Relay engine is not yet wired to the transport layer.
- Fanout and peer selection are pluggable but not exercised end-to-end.
- Orphan pool tracks blocks but does not recursively reconstruct chains.
- Timeouts, retries, and compact blocks are deferred.

## Conclusion

Phase 8K implements a bounded, pull-based block relay layer that follows the
Phase 8J architecture. It validates every received block through the ledger,
commits only valid blocks via storage, and suppresses duplicates and resource
abuse. The relay layer does not decide blockchain truth.
