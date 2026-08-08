# Sync Threat Model

Version: `chainbreaker-net-v1`  
Status: **Phase 8H design document — architecture/specification only**

---

## 1. Purpose

This document identifies the adversarial threats that appear when Chain-Breaker
nodes synchronize blockchain data. It focuses on threats to the sync process
itself, not to consensus rules.

---

## 2. Attacker model

Capabilities assumed:

- Control one or more peers.
- Send arbitrary `HEADERS` and `BLOCK` responses.
- Delay, drop, or reorder messages.
- Claim arbitrary best heights and chain work values.
- Consume some bandwidth of the target.

Not assumed:

- Breaking SHA-256 or proof-of-work.
- Controlling all independent sync peers simultaneously.
- Compromising the local storage or consensus code.

---

## 3. Threats

### 3.1 Fake high-work chain advertisement

**Description:** A peer claims to have a chain with more accumulated work
than the local chain, but the headers are invalid or fabricated.

**Impact:**
- Wastes bandwidth on block download.
- May temporarily confuse sync scheduling.

**Mitigations:**
- Validate every header before accepting work claims.
- Compute work from validated headers, not from peer claims.
- Use the reorg engine to compare chains, not sync heuristics.

---

### 3.2 Invalid header flooding

**Description:** A peer sends a continuous stream of invalid headers.

**Impact:**
- CPU exhaustion from validation.
- Bandwidth waste.

**Mitigations:**
- Validate headers incrementally; stop at first failure.
- Per-peer and global rate limits on sync messages.
- Score penalties and bans for repeated invalid responses.
- `MAX_HEADERS_RESPONSE` bounds response size.

---

### 3.3 Invalid block flooding

**Description:** A peer sends invalid full blocks after promising a valid
header chain.

**Impact:**
- Bandwidth waste.
- CPU waste on full block validation.

**Mitigations:**
- Validate headers first; only download blocks for validated header chains.
- Validate each block immediately on receipt.
- Bound outstanding block requests and memory.
- Score penalties and bans.

---

### 3.4 Bandwidth exhaustion

**Description:** A peer sends large or frequent sync responses.

**Impact:**
- Network saturation.
- Denial of service.

**Mitigations:**
- Per-peer byte limits.
- Global sync byte budget.
- Bounded `max_results` and `MAX_BLOCKS_RESPONSE`.
- Timeouts and backpressure.

---

### 3.5 Peer eclipse-assisted attacks

**Description:** An attacker surrounds a node with malicious peers and feeds
it an invalid or low-work alternate chain.

**Impact:**
- Target node remains on a fork.
- Target may reject valid data from the real network.

**Mitigations:**
- Header-first sync from multiple independent peers.
- Work comparison across peers.
- Peer diversity rules (Phase 8G).
- Future: checkpoints and anchor peers.

---

### 3.6 Slow peer attacks

**Description:** A peer responds correctly but extremely slowly, stalling
progress.

**Impact:**
- Sync never completes.
- Other peers are underutilized.

**Mitigations:**
- Request timeouts.
- Retry with another peer.
- Parallel outstanding requests to multiple peers.
- Score penalties for timeouts.

---

### 3.7 Malformed sync responses

**Description:** A peer sends envelopes that parse but contain nonsensical
sync payloads.

**Impact:**
- Crashes or resource exhaustion if not handled.

**Mitigations:**
- Strict schema validation for `GET_HEADERS`, `HEADERS`, `GET_BLOCK`, `BLOCK`.
- Envelope parser rejects malformed frames (Phase 8B).
- Score penalties.

---

### 3.8 Resource exhaustion

**Description:** A peer triggers excessive memory or CPU use through sync.

**Impact:**
- OOM.
- CPU starvation.

**Mitigations:**
- Bounded queues and caches.
- Memory limits for in-flight blocks.
- Header validation before block allocation.
- Rate limits.

---

### 3.9 Deep reorganization abuse

**Description:** An attacker repeatedly advertises deep reorganizations to
force expensive rollbacks.

**Impact:**
- Storage churn.
- CPU and I/O load.

**Mitigations:**
- Reorg certification (Phase 7H) requires significant work before commit.
- Score penalties for peers that frequently trigger invalid reorgs.
- Future checkpoints to bound rollback depth.

---

## 4. Invariants

1. Sync never accepts data as canonical without consensus validation.
2. Sync never writes unvalidated blocks to storage.
3. Work comparison is performed by the reorg engine, not sync.
4. Peer claims are untrusted until validated.
5. Sync state is rebuilt from committed storage after a crash.
