# Network Adversarial Certification Plan

Version: `chainbreaker-net-v1`  
Status: **Phase 8L — adversarial certification plan**

---

## 1. Purpose

This document defines the plan for certifying the Chain-Breaker network stack
against adversarial conditions before adding transaction/mempool or public-node
surfaces.

---

## 2. Scope

The certification covers the combined behavior of:

- discovery and peer table (`chainbreaker/network/discovery/`)
- transport and handshake (`chainbreaker/network/transport/`)
- chain sync (`chainbreaker/network/sync/`)
- block relay (`chainbreaker/network/relay/`)
- connection manager (`chainbreaker/network/transport/manager.py`)

It does not cover transaction relay, mempool, fee logic, mining communication,
or wallet functionality.

---

## 3. Certification scenarios

| ID | Scenario | Target behavior |
|----|----------|-----------------|
| A1 | Malicious peer swarm | Peer table stays bounded; diversity rules enforced. |
| A2 | Fake high-work chain | Sync engine delegates to consensus; no commitment. |
| A3 | Relay flooding | Rate limits and duplicate cache prevent amplification. |
| A4 | Repeated inventory | Duplicate announcements are ignored. |
| A5 | Unknown block request | GET_BLOCK for missing block returns `unknown`. |
| A6 | Sync interrupt | State machine resets cleanly without corrupting storage. |
| A7 | Peer churn | Repeated add/remove leaves table in consistent state. |
| A8 | Reconnect storm | Connection capacity is respected; slots never negative. |

---

## 4. Test harness

The certification tests use a `SimulatedPeer` class that instantiates:

- a fresh `Ledger` and genesis block
- a temp `FlatFileStorageBackend`
- a `DiscoveryManager` with a bounded `PeerTable`
- a `SyncEngine`
- a `RelayEngine`
- a `ConnectionManager`

Each test drives one or more components through adversarial inputs and asserts
the combined behavior.

---

## 5. Acceptance criteria

- All adversarial tests pass.
- No component crashes or corrupts another component's state.
- Resource limits are never exceeded.
- Consensus validation remains the gate for block acceptance.
- Relay never commits unvalidated blocks.

---

## 6. Out of scope

- Transaction relay and mempool.
- NAT traversal.
- Public node operation.
- Economic / fee logic.
- Mining pool communication.
