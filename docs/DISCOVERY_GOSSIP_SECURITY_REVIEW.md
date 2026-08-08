# Discovery and Gossip Security Review

Version: `chainbreaker-net-v1`  
Status: **security review for Phase 8G — peer discovery + gossip implementation**

---

## 1. Scope

This review covers:

- `chainbreaker/network/discovery/`
- `chainbreaker/network/gossip/`
- `chainbreaker/network/constants.py` additions for gossip
- `chainbreaker/network/messages.py` additions for `PEXMessage`
- `chainbreaker/network/codec.py` additions for `PEX`
- Tests under `tests/network/discovery/` and `tests/network/gossip/`

Phase 8G implements the design from Phase 8F and still excludes sync, relay,
mempool, mining communication, and public node operation.

---

## 2. Threats and mitigations

### 2.1 Peer table overflow

**Threat:** An attacker tries to fill the peer table with useless records to
hide legitimate peers.

**Mitigation:**
- `PeerTable` enforces `max_entries` (default 4096).
- Eviction prefers banned peers and same-source, lower-score records; equal-or-
  better records are not churned.
- Duplicate `(host, port)` entries are merged, not duplicated.

### 2.2 Source and prefix diversity bypass

**Threat:** An attacker advertises many peers from the same source or IP prefix
to eclipse a node.

**Mitigation:**
- `select_candidates()` enforces `max_same_source_ratio` and
  `max_same_prefix_peers`.
- Default limits are conservative (`max_same_prefix_peers=2`).

### 2.3 Gossip amplification

**Threat:** A single message is forwarded indefinitely.

**Mitigation:**
- TTL is decremented on each forward; zero-TTL messages are accepted but not
  forwarded.
- `hop_count` is capped at `max_hops`.
- Fanout is capped at `gossip_fanout` (default 3).
- Duplicate suppression prevents re-propagation of the same payload.

### 2.4 Duplicate cache exhaustion

**Threat:** An attacker sends many unique messages to exhaust the cache.

**Mitigation:**
- `GossipCache` is bounded by `max_entries` (default 50,000).
- Entries expire after `ttl_seconds` (default 300).
- FIFO eviction when the cache is full.

### 2.5 Rate-limit evasion

**Threat:** A peer sends gossip just below the rate limit but still wastes
bandwidth.

**Mitigation:**
- Per-peer, global message, and global byte token buckets are enforced.
- `max_payload_size` rejects oversized messages before parsing.

### 2.6 Malformed gossip payloads

**Threat:** A peer sends payloads that crash the forward-decay logic.

**Mitigation:**
- TTL/hop extraction is defensive (`try/except` with fallback).
- Invalid payloads return `ttl=0, hop_count=0`, causing no forward.
- JSON parsing exceptions are caught and handled.

### 2.7 Score manipulation

**Threat:** A peer tries to game the scoring model.

**Mitigation:**
- Scores are local-only; no node accepts reputation reports from peers.
- Handshake success/failure changes are deterministic and bounded.
- Bans escalate but allow recovery, preventing permanent false positives.

---

## 3. Limitations and future work

- No persistent score database across restarts.
- No cryptographic node identity.
- No DNS seed implementation yet.
- No PEX wire message dispatch yet; the message type and payload class exist.
- No eclipse-detection anchor logic beyond diversity rules.
- No transport encryption.

---

## 4. Consensus boundary

Discovery and gossip do not import or depend on:

- ledger
- storage
- registry
- archive
- governance
- consensus state

They only manage peer metadata and bounded message propagation.
