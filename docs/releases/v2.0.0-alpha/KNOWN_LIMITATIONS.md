# Known Limitations — v2.0.0-alpha

These items are intentionally outside the alpha freeze. They are scheduled for future milestones.

1. **Networking layer**
   - No peer-to-peer gossip.
   - No transport encryption.
   - No bootstrap/discovery.

2. **Storage backends**
   - Single flat-file persistence.
   - No pluggable backend interface.
   - No archival compaction or migration tooling.

3. **Reorganization engine**
   - No chain reorg handling.
   - No fork-choice rule beyond longest valid chain.
   - No rollback/rewind operator commands.

4. **Production operations**
   - No metrics or observability.
   - No operator runbook.
   - No backup/restore procedure beyond filesystem copy.

5. **External review**
   - No third-party security audit completed.
   - No formal verification of consensus invariants.
