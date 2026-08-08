# Peer Scoring Model

Version: `chainbreaker-net-v1`  
Status: **Phase 8F design document — architecture/specification only**

---

## 1. Purpose

This document defines how Chain-Breaker evaluates the behavior of connected
peers and uses those evaluations to decide whom to connect to, whom to forward
messages to, and whom to disconnect or ban.

---

## 2. Score design

Each known peer has a score in the range `[0, 1000]`.

| Range | Interpretation |
|-------|----------------|
| 900–1000 | Excellent — preferred for connections and forwarding |
| 700–899  | Good — normal peer |
| 500–699  | Neutral — acceptable but not preferred |
| 200–499  | Poor — connection limited, closely watched |
| 0–199    | Banned or near-banned — rejected |

Initial score for a new peer: `500`.
Trusted manual/bootstrap peers start at `900` but can still be penalized.

---

## 3. Positive events

| Event | Score delta | Notes |
|-------|-------------|-------|
| Successful handshake | +50 | one-time per session |
| Valid PONG response | +5 | capped per minute |
| Accepted non-duplicate gossip | +2 | capped per minute |
| Long-lived stable connection | +10 per hour | capped at +100 per day |

---

## 4. Negative events

| Event | Score delta | Notes |
|-------|-------------|-------|
| Failed handshake | −100 | per attempt |
| Wrong network/genesis/version | −200 | plus immediate disconnect |
| Malformed envelope | −100 | per message |
| Duplicate gossip spam | −20 | per duplicate |
| Rate limit violation | −50 | per window |
| Timeout/no response | −30 | per incident |
| Unsolicited message class | −100 | e.g., TX in V1 |
| Buffer/memory limit abuse | −200 | immediate disconnect |
| Protocol state violation | −250 | immediate disconnect |

---

## 5. Ban policy

A peer is banned when its score falls below `100`.

- Banned peers are removed from the active connection set.
- Banned peers are not selected for new outbound connections.
- Ban state is keyed by `peer_id` and endpoint.
- Ban duration is dynamic:
  - First ban: 1 hour
  - Second ban: 24 hours
  - Third ban: 7 days
  - Further bans: permanent unless manually cleared

---

## 6. Recovery

Scores recover slowly over time:

- Passive recovery: `+1` point per hour while not connected, up to a ceiling of
  `300` for banned peers and `500` for non-banned peers.
- Active recovery: a successful re-handshake after a ban gives `+200` (one
  time), lifting the peer out of ban range if enough time has passed.

This prevents permanent false positives while still preserving memory of
abuse.

---

## 7. Scoring safeguards

1. **No negative feedback loops from one peer.** Score changes from a single
   peer are bounded per minute to prevent a malicious peer from manipulating
   reputation of others by relaying false reports.
2. **Local-only scores.** A node never trusts another node’s score report. All
   scores are derived from direct observation.
3. **Manual override.** Operator-configured trusted peers are never auto-banned,
   though scoring still tracks their behavior for diagnostics.
4. **Decay.** Very high scores decay slowly toward `900` to prevent stale
   preference for long-gone excellent peers.

---

## 8. Connection selection scoring

When choosing outbound connections:

1. Filter out banned and recently failed peers.
2. Sort by score descending, then by recency.
3. Ensure source and prefix diversity.
4. Select `max_outbound_connections` peers.

When choosing gossip forward targets:

1. Filter out peers that already sent this gossip.
2. Filter out banned/low-score peers.
3. Select up to `gossip_fanout` peers by score-weighted random sampling.

---

## 9. Threats

### Reputation poisoning

A peer cannot change another peer’s score because scores are local-only.

### Strategic good behavior

An attacker may behave well to build score, then attack. Defenses:
- score recovery is slow
- severe violations still cause immediate disconnect and long bans
- high score does not bypass envelope or protocol validation

### False positive bans

A transient network issue could ban a legitimate peer. Defenses:
- recovery mechanism
- manual trusted-peer exemption
- ban durations escalate, not permanent on first offense

---

## 10. Deferred to future phases

- persistent score database across restarts
- cryptographic identity-bound reputation
- shared threat intelligence (with extreme caution)
- adaptive scoring based on network-wide observations
