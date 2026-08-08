# Network Consensus Boundary

Version: `chainbreaker-net-v1`  
Status: **architecture specification — no implementation yet**

---

## 1. Purpose

This document is the most important architectural contract in Phase 8. It draws
a hard line between what the network layer may do and what it may never do.

The rule is:

> The network transports consensus. The network does not define consensus.

---

## 2. What networking may do

The network layer is allowed to:

1. **Deliver blocks.** It may request, receive, and relay fully validated
   `BlockV2` objects.
2. **Deliver transactions.** It may carry transactions that the consensus engine
   will validate.
3. **Discover peers.** It may help the node learn about candidate peers to
   connect to (future phase; not in V1).
4. **Request data.** It may ask peers for headers, blocks, archive objects, or
   inventory.
5. **Relay information.** It may announce valid data to peers after local
   validation.
6. **Disconnect peers.** It may close connections that violate protocol rules or
   limits.
7. **Inform sync priority.** It may use `best_chain_work` from peers to decide
   which peers are most likely to have useful data. This is advisory only.

---

## 3. What networking may never do

The network layer must never:

1. **Decide valid blocks.** Validity is determined by Protocol V2.
2. **Modify state rules.** No network message may alter registry, monetary, or
   contract state transition rules.
3. **Override fork choice.** The canonical chain is the one with the greatest
   accumulated valid work, computed locally.
4. **Alter registry state.** Registry state is replayed from canonical blocks,
   never received from peers.
5. **Change archive truth.** Archive objects are content-addressed; a peer may
   provide bytes, but the hash is the authority.
6. **Relax validation.** A block from a peer must pass the exact same
   validation as a block mined locally.
7. **Influence consensus parameters.** Genesis, network ID, retarget rules,
   halving schedules, and validation thresholds are constants.
8. **Trust peer metadata.** `best_height`, `best_chain_work`, feature bits, and
   limits are advisory; the node verifies everything itself.

---

## 4. Required invariant

For any valid transition the network proposes, the same transition must be
possible from purely local input:

```
valid_network_transition(blocks) ⇔ valid_local_transition(blocks)
```

In other words, if the network disappeared and the node had the same blocks on
disk, the resulting canonical state would be identical.

---

## 5. Consequences of the boundary

### 5.1 No peer majority

A node must never adopt a chain because a majority of peers claim it is valid.
It adopts a chain because it has the greatest accumulated valid work.

### 5.2 No peer authority

No peer is authoritative. A peer is a data source. The consensus engine is the
authority.

### 5.3 Network failures are not consensus failures

If all peers are malicious or unreachable, the node may be stale or eclipsed,
but it must not corrupt its own state. Its canonical chain remains the best
chain it has validated.

### 5.4 Malformed network data is not consensus data

A message that fails envelope validation never reaches the consensus engine.
It is discarded at the network boundary.

---

## 6. Engineering implication

The consensus core must be buildable, testable, and runnable with **no network
dependency**. The network layer is an optional wrapper around the core.

This means:

- `chainbreaker/reorg.py` must not import any networking module.
- `chainbreaker/storage/backend.py` must not import any networking module.
- `chainbreaker/consensus/protocol_v2.py` must not import any networking module.
- Future networking code may import consensus modules; the reverse is forbidden.

---

## 7. Violation examples

The following would violate this boundary:

- A peer sends a "SET_GENESIS" message.
- A peer sends a "TRUST_THIS_CHAIN" message.
- A peer votes on which fork is canonical.
- The sync layer skips validation for blocks from long-lived peers.
- The network layer modifies `max_reorg_depth` based on peer pressure.
- A peer proposes a new difficulty retarget formula.

None of these may ever exist.

---

## 8. Why this boundary matters

Most catastrophic blockchain bugs come from conflating network opinion with
consensus truth. Eclipse attacks, Sybil attacks, and 51% attacks exploit that
confusion.

Chain-Breaker's network layer will be untrusted by design. The consensus engine
is a fortress. The network may knock on the door; it may not open it.
