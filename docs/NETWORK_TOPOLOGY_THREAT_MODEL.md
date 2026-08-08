# Network Topology Threat Model

Version: `chainbreaker-net-v1`  
Status: **Phase 8F design document — architecture/specification only**

---

## 1. Purpose

This document identifies the threats that appear once Chain-Breaker has peer
discovery, gossip, and a live network topology. It does not propose full
mitigations; it documents assumptions and design responses so that later
phases build on a clear threat model.

---

## 2. Attacker model

Capabilities assumed:

- Run many nodes with arbitrary IP addresses.
- Control a subset of network links.
- Eavesdrop on unencrypted traffic (V1 has no transport encryption).
- Send arbitrary messages that pass envelope validation.
- Delay, reorder, or drop messages.

Not assumed (for V1):

- Breaking SHA-256.
- Compromising all bootstrap seeds simultaneously.
- Controlling the majority of independent internet paths.

---

## 3. Threats

### 3.1 Sybil attack

**Description:** An attacker creates a large number of identities or endpoints
to dominate a victim’s peer table, gossip fanout, or discovery sources.

**Impact:**
- Eclipse isolation
- Censorship of messages
- Disproportionate resource consumption

**Mitigations in design:**
- source diversity limits
- IP prefix diversity limits
- independent bootstrap sources
- scoring and dynamic bans

**Residual risk:** Without cryptographic identity, IP addresses remain cheap and
creating many Sybil nodes is feasible. Later phases will add identity cost.

---

### 3.2 Eclipse attack

**Description:** An attacker surrounds a target node with attacker-controlled
peers so that all inbound/outbound traffic passes through the attacker.

**Impact:**
- Target sees only attacker-approved chain state (once sync exists).
- Target can be partitioned from the rest of the network.

**Mitigations in design:**
- maintain connections to independent bootstrap/DNS seeds
- source diversity
- periodic random reconnections
- cache of previously good peers from independent sources

**Residual risk:** A patient attacker with enough addresses and long uptime can
still eclipse a node that has few independent peer sources.

---

### 3.3 Gossip flooding

**Description:** An attacker injects a large volume of valid-but-useless gossip
messages to consume bandwidth and CPU.

**Impact:**
- Bandwidth exhaustion
- Cache pollution
- Legitimate messages delayed

**Mitigations in design:**
- TTL/hop limits
- small fanout
- per-peer and global rate limits
- duplicate suppression
- scoring penalties for abuse

**Residual risk:** A widely distributed attacker can still generate observable
load; global rate limits bound the damage.

---

### 3.4 Duplicate suppression abuse

**Description:** An attacker sends carefully chosen messages to maximize cache
size or force premature eviction of useful entries.

**Impact:**
- Cache thrashing
- Re-propagation of old messages

**Mitigations in design:**
- bounded cache size
- FIFO + random eviction
- message-size limits
- rate limits

---

### 3.5 Topology manipulation

**Description:** An attacker advertises peers selectively to steer network
structure, e.g., pointing many nodes toward a small attacker-controlled cluster.

**Impact:**
- Centralization
- Censorship points
- Partition recovery difficulty

**Mitigations in design:**
- PEX bounded responses
- no single mandatory discovery authority
- diversity enforcement
- random sampling from peer table

---

### 3.6 Time and liveness manipulation

**Description:** An attacker drops PING/PONG, slows responses, or forges
reachability information to degrade perceived network health.

**Impact:**
- Unnecessary peer rotation
- False positives in availability monitoring

**Mitigations in design:**
- multiple independent heartbeat samples
- score penalties only after repeated timeouts
- no consensus decisions based on heartbeat

---

### 3.7 Seed compromise

**Description:** A bootstrap DNS seed or static seed is compromised and returns
only attacker addresses.

**Impact:**
- New nodes connect only to attacker infrastructure.

**Mitigations in design:**
- multiple independent seeds
- cached and manual peers as anchors
- seeds provide liveness, not trust

---

## 4. Design invariants

1. **No single peer is trusted.** Every message is validated independently.
2. **Scores are local.** No node accepts another node’s reputation report.
3. **Gossip is bounded.** TTL, fanout, and rate limits make amplification finite.
4. **Discovery is diverse.** Multiple independent sources are mandatory.
5. **Consensus is isolated.** Topology state never influences block validation,
   chain selection, or state transitions.

---

## 5. Future work

- Transport encryption (TLS or noise protocol).
- Cryptographic node identities and signed peer advertisements.
- Deterministic anchor peers resistant to eclipse.
- Peer-exchange privacy improvements.
- Out-of-band chain-state checkpoints for eclipse detection.
