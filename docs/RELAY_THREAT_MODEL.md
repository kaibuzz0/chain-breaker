# Relay Threat Model

Version: `chainbreaker-net-v1`  
Status: **Phase 8J design document — architecture/specification only**

---

## 1. Purpose

This document analyzes adversarial threats specific to block relay.

---

## 2. Attacker model

An attacker may control one or more peers and can:

- send arbitrary `INV_BLOCK` messages
- send invalid `BLOCK` responses
- delay or withhold responses
- claim to have blocks they do not have
- flood the network with announcements

The attacker cannot:

- break SHA-256 or proof-of-work
- control all peers of the target
- modify the target's consensus code

---

## 3. Threats

### 3.1 Block flooding

**Description:** An attacker announces a large number of block hashes.

**Impact:** Bandwidth and CPU consumption; request amplification.

**Mitigations:**
- `INV_BLOCK` size limit (256 hashes).
- Per-peer and global rate limits.
- Duplicate cache prevents re-requesting seen hashes.
- Validation before forwarding prevents amplification.

---

### 3.2 Duplicate amplification

**Description:** Same block is announced repeatedly.

**Impact:** Wasted bandwidth and CPU.

**Mitigations:**
- `RelaySeenCache` with 2-hour expiry and 50,000-entry limit.
- Ignore `INV_BLOCK` for cached hashes.
- FIFO eviction when cache is full.

---

### 3.3 Orphan flooding

**Description:** Attacker sends many blocks with unknown or fabricated
ancestors.

**Impact:** Memory exhaustion; useless parent requests.

**Mitigations:**
- Orphan pool bounded to 1024 entries.
- Orphan age limit 2 hours.
- One parent request per orphan.
- Orphans are not relayed.

---

### 3.4 Bandwidth exhaustion

**Description:** Attacker requests or sends large blocks frequently.

**Impact:** Network saturation.

**Mitigations:**
- `max_total_bytes` hints.
- `MAX_BLOCKS_RESPONSE` (32) limits blocks per response.
- Per-peer and global byte budgets.
- Backpressure when budget exhausted.

---

### 3.5 Invalid block injection

**Description:** Attacker sends a block that fails validation.

**Impact:** CPU waste; potential storage poisoning if not caught.

**Mitigations:**
- Validate every `BLOCK` before accepting, storing, or relaying.
- Invalid blocks are dropped and peer score reduced.
- `REJECT_BLOCK` provides explicit feedback (optional).

---

### 3.6 Eclipse-assisted relay attacks

**Description:** Attacker surrounds a node and feeds only attacker blocks.

**Impact:** Target node adopts wrong chain.

**Mitigations:**
- Multiple independent peers.
- Peer diversity rules from Phase 8G.
- Sync engine still runs for catch-up.
- Future: anchor blocks and checkpoint enforcement.

---

### 3.7 Withholding / slow relay

**Description:** Attacker receives a block but delays or refuses to relay.

**Impact:** Network partition; slower propagation.

**Mitigations:**
- Multiple peers receive announcements.
- Parallel `GET_BLOCK` requests.
- Timeouts and retries.

---

## 4. Invariants

1. A block is never relayed before local validation.
2. A block is never stored before validation.
3. Orphan pool never grows unbounded.
4. Duplicate cache prevents re-propagation loops.
5. Relay never overrides consensus or reorg decisions.
