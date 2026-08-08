# Reorg Adversarial Review

Version: chainbreaker-scripture-v2  
Status: **design-only milestone**  
Branch: `phase7g-reorg-state-branching-design`

---

## 1. Scope

This document enumerates adversarial scenarios against the reorg and state-branching design. Each scenario is classified as prevented, mitigated, or requiring future work, with the specific design mechanism that addresses it.

No implementation code is changed in this phase. These scenarios will become test cases in Phase 7I (`phase7i-reorg-fault-and-fork-certification`).

---

## 2. Fork-choice attacks

### 2.1 Height-only branch preference

**Attack:** An adversary mines a chain with lower total work but greater height and convinces the node to reorg.

**Prevention:** Core invariant selects by **accumulated work**, not height. A candidate with `work <= current_work` is ignored even if its height is greater.

### 2.2 Equal-work oscillation

**Attack:** Two branches with equal work alternate as tips, causing the node to flip back and forth.

**Prevention:** A candidate with `work == current_work` does **not** trigger reorg. The existing canonical tip wins ties. Nodes must never prefer a candidate on tie.

### 2.3 Selfish-mining variant

**Attack:** Adversary withholds blocks, then releases a private chain with slightly more work to replace public history.

**Mitigation:** Work comparison correctly accepts the heavier chain. Local `max_reorg_depth` policy limits how deep a surprise rewrite can be accepted without operator override.

---

## 3. State contamination attacks

### 3.1 Registry state leak across branches

**Attack:** Transactions from the orphaned branch affect the candidate branch's registry root.

**Prevention:** Candidate registry state is replayed from the **common ancestor state** in an isolated scratch object. The current canonical suffix is never used as a starting point for the candidate replay.

### 3.2 Stale registry root accepted

**Attack:** A block carries a registry root from a different branch or height.

**Prevention:** Each candidate block's `registry_root` is compared against `registry_root(state_at(height))` derived from replaying the candidate branch. Mismatch rejects the block and the branch.

### 3.3 Snapshot override of replay truth

**Attack:** A malicious or stale snapshot is used as the starting state for replay, causing the node to accept an invalid branch.

**Prevention:** Snapshots are accelerators only. The design requires that any snapshot used as a starting point is verified by replaying a suffix of canonical blocks back to a trusted height (or genesis). A snapshot that disagrees with replay is discarded.

---

## 4. Storage and durability attacks

### 4.1 Partially durable reorg

**Attack:** A crash occurs after some connect-set blocks are published but before `HEAD` is updated; node restarts into an inconsistent state.

**Prevention:** Only `HEAD` determines canonical tip. Recovery uses `safe_height = min(HEAD, last_commit)` and rolls back derived data. Connect-set blocks without a durable `HEAD` are not canonical.

### 4.2 HEAD points beyond durable blocks

**Attack:** `HEAD` is modified to point to a height whose canonical files are missing or corrupt.

**Prevention:** Recovery walks backward from `HEAD`, verifying each block's header hash and linkage. It rolls back to the highest verified height and rewrites `HEAD`.

### 4.3 Orphaned blocks resurrected as canonical

**Attack:** After a reorg, old disconnect-set blocks are somehow treated as canonical again because indexes or caches still reference them.

**Prevention:** Derived indexes are rebuilt from canonical files after every tip switch. Caches are invalidated. Disconnect-set blocks remain on disk but are not referenced by `HEAD` or indexes.

### 4.4 Two competing HEADs

**Attack:** Two `HEAD` files exist (e.g., via symlink or file-system race).

**Prevention:** Single canonical `HEAD` path; atomic replace; single-writer lock prevents concurrent writers.

---

## 5. Validation bypass attacks

### 5.1 Skipped median-past time check

**Attack:** Candidate branch uses timestamps that violate median-past rules but otherwise has more work.

**Prevention:** Full Protocol V2 block validation is applied to every block in the connect set, including timestamp and target checks.

### 5.2 Retarget manipulation

**Attack:** A branch manipulates timestamps to force an easier target, then builds more blocks with lower per-block difficulty.

**Prevention:** Work comparison uses actual `target` from each header; `2**256 / (target + 1)` reflects real expended work. A manipulated retarget that lowers per-block difficulty produces lower per-block work.

### 5.3 Oversized connect set

**Attack:** A candidate branch contains a block with an invalid transaction payload or size.

**Prevention:** Size limits and transaction schema validation are applied per block. Any invalid block rejects the entire branch.

---

## 6. Denial-of-service vectors

### 6.1 Header flood

**Attack:** Adversary sends many low-work headers to consume validation resources.

**Mitigation:** Basic PoW check is cheap and applied first. Headers that fail PoW are dropped immediately. Rate-limiting and `max_reorg_depth` bound further processing.

### 6.2 Long but low-work branches

**Attack:** Adversary builds a long chain of very low-difficulty blocks and tries to force the node to fetch and replay them.

**Mitigation:** Work comparison rejects them before deep replay if their total work is not greater. `max_reorg_depth` and fetch windows bound resource usage.

### 6.3 Missing-ancestor fetch loop

**Attack:** Candidate tips reference a long chain of unknown ancestors, causing unbounded fetches.

**Mitigation:** Fetch depth is bounded by local policy. If the common ancestor cannot be found within the bound, the candidate is rejected.

---

## 7. Attestation and archive attacks across reorgs

### 7.1 Orphaned attestation invalidated

**Attack:** A user relies on an attestation; after a reorg, the node incorrectly reports it as invalid.

**Prevention:** Attestation validity depends on the registry state at the claimed `block_height`. If the block at that height is unchanged in the new canonical chain, the attestation remains valid. If the block was orphaned, the attestation is still verifiable against the registry state at that historical height, but it does not prove canonical-chain membership.

### 7.2 Archive object deleted after reorg

**Attack:** A manifest committed on the orphaned branch references an archive object that is later pruned.

**Mitigation:** Pruning policy must retain archive objects referenced by any unrevoked attestation on any known branch. Content-addressing allows multiple branches to share the same object safely.

### 7.3 Attestation replay to wrong branch

**Attack:** A v1 attestation without block-height binding is moved to a different block.

**Prevention:** Phase 7G requires v2 attestations with `block_height` in the signed domain. v1 attestations are treated as deprecated and not accepted for new canonical proofs.

---

## 8. Policy and operator attacks

### 8.1 Overly restrictive `max_reorg_depth`

**Attack:** Operator sets `max_reorg_depth = 0`, preventing any reorg and effectively freezing the chain.

**Mitigation:** This is a local operator choice. The default will be reasonable (e.g., 1000 blocks), and operators can override. The node logs when a reorg is rejected due to depth.

### 8.2 Checkpoint contradiction

**Attack:** A future checkpoint mechanism conflicts with accumulated-work choice.

**Open question:** Checkpoints are not defined in this phase. If added later, they must be explicit local policy overrides, not consensus rules.

---

## 9. Test cases for Phase 7I

| # | Scenario | Expected behavior |
|---|----------|-------------------|
| 1 | Candidate with lower work but higher height | Reject |
| 2 | Candidate with equal work | No reorg |
| 3 | Candidate with greater work and valid state | Reorg |
| 4 | Registry root mismatch in connect set | Reject branch |
| 5 | Timestamp violation in connect set | Reject branch |
| 6 | Crash during `SWITCHING_TIP` | Recovery to old or new `HEAD`, no hybrid |
| 7 | Crash during `REBUILDING_DERIVED` | New `HEAD` durable; indexes rebuilt on restart |
| 8 | Malformed `HEAD` after reorg | Recovery ignores `HEAD`, uses journal/canonical files |
| 9 | Snapshot inconsistent with replay | Discard snapshot, replay from canonical blocks |
| 10 | Attestation on orphaned block | Still valid if registry state at height is known |
| 11 | Archive object shared across branches | Content-addressing preserves object |
| 12 | Reorg deeper than `max_reorg_depth` | Reject unless operator override |
| 13 | Two candidates queued simultaneously | Process sequentially; second sees new canonical tip |
| 14 | Candidate's common ancestor is genesis | Valid deep chain accepted if work greater |
| 15 | Current tip orphaned, then same branch re-promoted | Accept if it regains more work |

---

## 10. Unresolved risks

1. **Work accumulation overflow:** `2**256 // (target + 1)` can overflow Python integers if not bounded; implementation must use Python's arbitrary-precision integers safely.
2. **Long reorg replay cost:** Replaying hundreds of blocks from a snapshot boundary may be slow; snapshot placement policy matters.
3. **Network amplification:** Future network design must not blindly forward low-work headers.
4. **Storage of alternate branches:** Keeping all known alternate branches could grow unbounded; pruning policy for branches is not yet defined.
