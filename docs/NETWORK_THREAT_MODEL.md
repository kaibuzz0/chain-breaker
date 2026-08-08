# Network Threat Model

Version: `chainbreaker-net-v1`  
Status: **architecture specification — no implementation yet**

---

## 1. Threat posture

Chain-Breaker's network layer operates under the assumption that **every peer
is potentially hostile**. This document lists the adversarial capabilities that
the protocol, sync strategy, and resource policy must resist.

The only trusted inputs are:

1. The local configuration (genesis hash, network ID, limits).
2. The frozen Protocol V2 validation rules.
3. Locally stored and verified chain data.

Everything received from a peer must be validated.

---

## 2. Identity attacks

### 2.1 Sybil peers

**Threat:** A single adversary opens many connections from different IP
addresses or identities to gain influence over a target node.

**Mitigation:**
- No peer identity or reputation in V1. Influence cannot be accumulated.
- Outbound connections are initiated by the local node based on operator
  configuration, not peer suggestion.
- Inbound connections are accepted only if the operator has enabled listening.
- No consensus weight is assigned to a peer count or a peer majority.

**Limitation:** V1 does not prevent a well-resourced adversary from filling all
inbound connection slots. That is addressed by connection limits and, in later
phases, peer reputation or proof-of-work connection cookies.

### 2.2 Fake identities

**Threat:** A peer claims a fake node ID, version, or capability set to exploit
implementation bugs.

**Mitigation:**
- V1 has no node ID field. There is no identity to fake.
- `protocol_version`, `network_id`, and `genesis_hash` are compared to local
  constants. Any mismatch causes immediate disconnection.
- `feature_bits` are advisory. Unknown bits are ignored.

**Limitation:** Later versions that add identities must design spoofing
resistance carefully.

### 2.3 Peer flooding

**Threat:** An adversary creates thousands of TCP connections to exhaust file
handles, memory, or CPU.

**Mitigation:**
- Hard `MAX_CONNECTIONS` limit.
- Per-IP connection limits.
- Connection rate limiting.
- Small read buffers until handshake completes.
- Pre-handshake connections do not allocate consensus objects.

**Limitation:** DDoS at the network or transport layer can still degrade service.
That is a hosting/operational concern, not a protocol concern.

### 2.4 Eclipse attacks

**Threat:** An adversary controls all of a node's peers and feeds it a private
fork or withholds blocks.

**Mitigation:**
- Outbound peer selection is operator-controlled; a node is not required to
  accept peer suggestions.
- Sync compares `best_chain_work` from multiple peers and independently validates
  all headers and blocks.
- No single peer can declare a chain canonical.

**Limitation:** A fully eclipsed node may not learn about the real chain until
it connects to an honest peer. Operational diversity of peers is required.

---

## 3. Transport attacks

### 3.1 Oversized messages

**Threat:** A peer sends a message whose payload length exceeds `MAX_PAYLOAD_BYTES`.

**Mitigation:**
- `payload_length` is read as a 4-byte big-endian integer.
- If it exceeds `MAX_PAYLOAD_BYTES` (2 MiB), the message is rejected and the
  peer is disconnected before the payload is read.

### 3.2 Malformed length prefixes

**Threat:** A peer sends a length prefix that claims a payload larger than the
remaining bytes, causing hangs or memory spikes.

**Mitigation:**
- Enforce payload length limit before allocation.
- Use bounded reads with timeouts.
- If the declared payload is not received within the read timeout, disconnect.

### 3.3 Amplification

**Threat:** A peer sends a small request that triggers a large response.

**Mitigation:**
- Response size limits are enforced (`MAX_HEADERS_RESPONSE`,
  `MAX_BLOCKS_RESPONSE`).
- Batch sizes are bounded.
- `GET_BLOCKS` may specify `max_total_bytes`.
- A node may refuse requests that would generate oversized responses.

### 3.4 Slow peers

**Threat:** A peer opens a connection and sends data very slowly, holding
resources indefinitely.

**Mitigation:**
- Per-connection read/write timeouts.
- Idle timeout after handshake.
- Maximum time to complete a request-response exchange.

### 3.5 Connection exhaustion

**Threat:** Legitimate or malicious peers consume all available connection
slots.

**Mitigation:**
- `MAX_CONNECTIONS` limit.
- Separate inbound/outbound quotas.
- Preference for outbound, operator-trusted peers.
- Close least-useful connections when slots are scarce.

---

## 4. Consensus attacks

### 4.1 Fake high-work chains

**Threat:** A peer claims a chain with enormous accumulated work that the local
node cannot verify without downloading everything.

**Mitigation:**
- `best_chain_work` is advisory. The sync layer downloads headers first and
  validates accumulated work independently.
- A peer cannot force a reorg. The reorg engine validates every candidate block
  before switching canonical tip.
- Equal-work chains do not switch automatically.

### 4.2 Invalid block spam

**Threat:** A peer sends blocks that fail Protocol V2 validation, wasting
bandwidth and CPU.

**Mitigation:**
- All blocks are validated before acceptance.
- Invalid blocks are not stored, relayed, or applied to state.
- Repeated invalid sends increase the peer's ban score.

### 4.3 Fork flooding

**Threat:** A peer advertises many competing forks to confuse the sync layer.

**Mitigation:**
- Sync prioritizes headers with the most accumulated work.
- Only one chain is canonical at a time.
- Orphaned blocks may be kept locally but do not affect canonical state.
- `max_reorg_depth` is local policy, not consensus, and limits operational
  reorganization depth.

### 4.4 Reorg abuse

**Threat:** A peer alternates between two equal-work forks to cause repeated
reorgs.

**Mitigation:**
- Equal-work forks do not trigger a tip switch.
- Reorgs require strictly greater accumulated valid work.
- A reorg cannot bypass candidate validation.

### 4.5 Alternate genesis attempts

**Threat:** A peer tries to connect using a different genesis hash.

**Mitigation:**
- Genesis hash is a local constant.
- HELLO with a mismatched genesis hash is rejected immediately.
- There is no negotiation.

---

## 5. Resource attacks

### 5.1 Memory exhaustion

**Threat:** A peer sends messages that force large allocations.

**Mitigation:**
- All size limits are enforced before allocation.
- Bounded read buffers.
- No unbounded queues for incoming messages.
- Reject or drop messages that exceed per-peer memory budgets.

### 5.2 CPU exhaustion

**Threat:** A peer sends expensive-to-validate payloads (e.g., invalid blocks
with valid-looking PoW, complex governance transactions).

**Mitigation:**
- Rate-limit expensive validation per peer.
- Validate PoW before deserializing heavy state.
- Use the same deterministic validation path for network and local data.

### 5.3 Disk exhaustion

**Threat:** A peer sends valid blocks faster than they can be pruned or
validated, filling disk.

**Mitigation:**
- Storage backend enforces chain limits and reorg depth policy.
- Orphaned blocks may be capped by local policy.
- Archive object storage is content-addressed; duplicates are not stored twice.

### 5.4 Bandwidth exhaustion

**Threat:** A peer requests the same data repeatedly or demands very large
batches.

**Mitigation:**
- Per-peer request rate limits.
- Response size caps.
- Throttle or disconnect peers that exceed bandwidth budgets.

---

## 6. Information leakage

### 6.1 Peer learning local state

**Threat:** A peer queries the node to learn which blocks, transactions, or
archive objects it holds.

**Mitigation:**
- Query responses are deterministic and do not reveal internal state beyond
  what is on the canonical chain.
- Operators may disable listening or restrict inbound peers.

### 6.2 Fingerprinting

**Threat:** An adversary probes implementation-specific behavior.

**Mitigation:**
- Strict envelope validation produces uniform rejection behavior.
- Error messages are generic; detailed reasons are logged locally only.

---

## 7. Remaining limitations

1. **No transport encryption.** Message payloads are not encrypted. A network
   observer can see which hashes and blocks are exchanged. Future phases will
   evaluate TLS or Noise.
2. **No peer authentication.** V1 does not verify who a peer is, only that it
   speaks the same protocol.
3. **No Sybil resistance beyond limits.** Connection limits reduce but do not
   eliminate Sybil flooding.
4. **No censorship resistance guarantees.** A node with only malicious peers
   may be eclipsed until it connects to an honest peer.

These limitations are documented so they are addressed deliberately, not
accidentally.
