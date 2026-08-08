# Network Architecture Adversarial Review

Version: `chainbreaker-net-v1`  
Status: **architecture specification — no implementation yet**

---

## 1. Review mission

Attempt to violate the network consensus boundary and find design flaws that
would allow a hostile peer to crash, confuse, or corrupt a Chain-Breaker node.

---

## 2. Threat questions and answers

### Q1: Can a malicious peer crash a node?

**Threat:** A peer sends malformed data, oversized messages, or unexpected
state transitions.

**Answer:** No, by design. The envelope parser validates magic, version,
network ID, length, and payload hash before the payload is parsed. Typed
payload validation enforces size and count limits. Any failure discards the
message and disconnects the peer; no consensus code is invoked.

**Mitigation:**
- `MAX_PAYLOAD_BYTES` enforced before allocation.
- All envelope fields validated before payload parsing.
- Unknown or oversized typed payloads rejected.
- Peer ban score incremented; repeat offenders disconnected and banned.

**Remaining limitation:** Transport-level crashes (e.g., kernel TCP bugs,
blocking I/O) are outside the protocol's scope. Future phases may use async
I/O and isolation to reduce this.

---

### Q2: Can a peer force unlimited memory allocation?

**Threat:** A peer sends a message with a huge length prefix or many nested
objects.

**Answer:** No. `payload_length` is bounded by `MAX_PAYLOAD_BYTES` before any
payload memory is allocated. Typed payload arrays (`headers`, `blocks`,
`hashes`) have hard count limits. Memory budgets and bounded read buffers apply
per connection.

**Mitigation:**
- Length-prefix check before allocation.
- Array count limits (`MAX_HEADERS_RESPONSE`, `MAX_BLOCKS_RESPONSE`,
  `MAX_INVENTORY_ENTRIES`, `MAX_LOCATOR_SIZE`).
- Per-peer read buffers and outstanding-byte limits.
- Global connection and memory budgets.

**Remaining limitation:** A node may still be memory-constrained by many small
valid messages. That is addressed by connection limits and rate limits.

---

### Q3: Can a peer influence the consensus outcome?

**Threat:** A peer claims a higher chain, sends a fake high-work fork, or tries
to override fork choice.

**Answer:** No. The network layer may propose blocks and headers, but the
consensus engine independently validates every header, computes accumulated
work, and decides canonical state. A peer's `best_chain_work` is advisory.
Reorgs use the same Phase 7H/7I engine for all inputs.

**Mitigation:**
- Local computation of accumulated work.
- Full validation of every downloaded block.
- Equal-work chains do not switch.
- `max_reorg_depth` is local policy.

**Remaining limitation:** An eclipsed node may not see the real chain until it
connects to an honest peer. Operational peer diversity is required.

---

### Q4: Can two honest nodes select different chains?

**Threat:** Network latency or partition causes nodes to see different data.

**Answer:** Temporary divergence is possible, but the algorithm is
deterministic. Once both nodes see the same set of valid blocks, they will
converge to the same canonical chain because fork choice depends only on
accumulated valid work, not on arrival order or peer identity.

**Mitigation:**
- Deterministic validation.
- Same genesis and rules.
- Equal-work rule prevents oscillation.

**Remaining limitation:** During a network partition, nodes on each side will
follow the best chain they can see. They will reconcile after the partition
heals.

---

### Q5: Can a peer poison archive history?

**Threat:** A peer sends a fake archive object that claims to be part of
canonical history.

**Answer:** No. Archive objects are content-addressed. A peer may provide any
bytes, but the node verifies `SHA-256(object) == requested_content_hash`.
Provenance is derived from canonical blocks, not from the peer.

**Mitigation:**
- Content hash verification.
- Provenance recomputed from canonical chain.
- Untrusted object bytes do not become canonical provenance.

**Remaining limitation:** A peer may withhold an archive object, causing the
node to retry from another peer.

---

### Q6: Can networking bypass frozen Protocol V2 rules?

**Threat:** A peer uses a network message type to alter validation rules.

**Answer:** No. The network message set is fixed. There is no message for
changing genesis, difficulty, retarget, or validation rules. The consensus core
does not import or depend on the network layer.

**Mitigation:**
- Fixed message type enumeration.
- Consensus core is network-free.
- Network layer only calls validation, never modifies rules.

**Remaining limitation:** A future protocol version could accidentally add a
dangerous message type. Code review must enforce the network-consensus boundary.

---

### Q7: Can synchronization create invalid local state?

**Threat:** A node downloads a chain that appears valid at the network layer
but corrupts state.

**Answer:** No. State is never downloaded. It is replayed locally from
canonical blocks. A block must pass the same validation as a locally mined
block before it can become canonical.

**Mitigation:**
- No state blobs from peers.
- Registry state replay from validated blocks.
- Atomic tip switching with journal commit ordering.
- Crash recovery rolls back to a safe committed height.

**Remaining limitation:** A bug in the replay logic could corrupt state, but
that would be a consensus bug, not a network bug.

---

## 3. Additional attack scenarios

### 3.1 Slowloris / partial message attacks

**Threat:** A peer sends envelope bytes very slowly or never completes a
message.

**Mitigation:** Per-connection read timeout and idle timeout. Incomplete
messages are discarded and the peer is disconnected.

### 3.2 Duplicate hash requests

**Threat:** A peer repeatedly requests the same blocks or archive objects.

**Mitigation:** Per-peer rate limits and request deduplication. Excessive
requests throttle or disconnect the peer.

### 3.3 Self-referential locator

**Threat:** A peer's `GET_HEADERS` start hash points to a block the node does
not have, causing wasted work.

**Mitigation:** Locator entries are validated against known blocks. Unknown
start hashes produce an empty response quickly.

### 3.4 Inventory spam

**Threat:** A peer sends giant `INV` messages or many announcements.

**Mitigation:** `MAX_INVENTORY_ENTRIES` and INV rate limits. Unsolicited large
INVs are rejected.

### 3.5 Refusing to respond

**Threat:** A peer accepts requests but never sends data.

**Mitigation:** Request timeouts and retry from other peers. No single peer is
required.

---

## 4. Residual risk register

| Risk | Severity | Mitigation status |
|------|----------|-------------------|
| Transport-level DDoS | Medium | Operational, out of protocol scope |
| Eclipse of all peers | Medium | Operational peer diversity |
| No transport encryption | Medium | Deferred to future phase |
| No peer identity | Medium | Deferred to future phase |
| Network partition divergence | Low | Deterministic convergence after heal |
| Future dangerous message type | Low | Code review + ADR 010 |

---

## 5. Conclusion

The Phase 8A network architecture is designed so that a hostile peer can at
worst waste bandwidth or force disconnection. It cannot crash the node, corrupt
state, alter consensus rules, or choose the canonical chain. The remaining
risks are operational or deferred to future hardening phases.
