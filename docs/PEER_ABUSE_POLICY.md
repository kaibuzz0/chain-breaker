# Peer Abuse Policy

Version: `chainbreaker-net-v1`  
Status: **Phase 8L — peer abuse policy**

---

## 1. Purpose

This document defines how the network layer responds to peer misbehavior.

---

## 2. Abuse categories

### 2.1 Inventory flooding

**Definition:** A peer sends more `INV_BLOCK` messages than the configured rate.

**Response:**
- Stop processing requests for the cooldown window.
- Reduce peer score.
- After repeated violations, ban the peer.

### 2.2 Invalid block relay

**Definition:** A peer announces or sends blocks that fail consensus
validation.

**Response:**
- Drop the block.
- Reduce peer score significantly.
- Do not forward the block.

### 2.3 Duplicate amplification

**Definition:** A peer repeatedly announces the same known block.

**Response:**
- Use duplicate cache to ignore re-announcements.
- Apply a small score penalty after many repeats.

### 2.4 Orphan flooding

**Definition:** A peer sends blocks with unknown parents.

**Response:**
- Add to bounded orphan pool.
- Request missing parent once.
- If parent does not arrive, evict orphan and reduce score.

### 2.5 Connection storm

**Definition:** A peer or address family rapidly opens many connections.

**Response:**
- Enforce `ConnectionManager` capacity.
- Reject or evict oldest connections.
- Ban source if it exceeds attempt limits.

### 2.6 Malformed messages

**Definition:** A peer sends messages that fail envelope or payload parsing.

**Response:**
- Disconnect after a small tolerance threshold.
- Reduce score.
- Do not propagate.

---

## 3. Recovery

- Score recovery follows `docs/PEER_SCORING_MODEL.md`.
- Bans have a default duration of 1 hour.
- Persistent offenders can be added to a local deny list.

---

## 4. Boundaries

Peer abuse policy is enforced by the network layer. It does not override
consensus decisions or storage rules.
