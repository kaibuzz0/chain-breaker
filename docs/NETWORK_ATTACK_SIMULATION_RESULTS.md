# Network Attack Simulation Results

Version: `chainbreaker-net-v1`  
Status: **Phase 8L — attack simulation results**

---

## 1. Method

Adversarial scenarios were exercised through the certification test harness in
`tests/network/adversarial/test_certification.py`. Each scenario is deterministic
and runs against a fresh simulated node.

---

## 2. Results

| Scenario | Result | Notes |
|----------|--------|-------|
| Peer swarm overflow | PASS | Table bounded to configured `max_entries`. |
| Fake high-work chain | PASS | Sync engine rejected; consensus not bypassed. |
| Relay inventory flood | PASS | Per-peer rate limit triggered. |
| Repeated inventory | PASS | Duplicate cache prevented re-request. |
| Unknown GET_BLOCK | PASS | Returned `unknown` without crash. |
| Sync interrupt/restart | PASS | State machine returned to `IDLE`. |
| Peer churn | PASS | Table size remained consistent. |
| Reconnect storm | PASS | Available slots stayed non-negative and bounded. |

---

## 3. Observations

- The peer table correctly raises `PeerTableFullError` and the harness handles it.
- Sync engine does not commit blocks that fail `Ledger.add_block_v2()`.
- Relay rate limits are enforced at the per-peer level.
- Duplicate suppression prevents request amplification.
- Storage and ledger state remain consistent across churn and restart.

---

## 4. Residual risks

The certification uses a single-node harness. Future work should include:

- multi-peer network simulations
- actual socket-based adversarial tests
- partition and eclipse scenarios with controlled topology
- restart during active relay/sync with real storage
- long-duration soak tests
