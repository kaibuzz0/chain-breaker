---
number: 010
title: Network Layer Is an Outer Subsystem
date: 2026-08-08
status: accepted
---

# ADR 010 — Network Boundary

## Context

Chain-Breaker is a deterministic archival ledger. Phase 7 hardened the core:
consensus, storage, recovery, and reorganization. Phase 8 will add networking
to allow peers to share blocks and archive objects.

The risk in this transition is that networking could accidentally become a
consensus dependency: a block might be accepted because of who sent it, or a
reorg might be triggered by peer pressure rather than by accumulated work.

## Decision

Networking is an **outer-layer subsystem**. It transports consensus-critical
data, but it does not participate in consensus decisions.

The consensus core must continue to be buildable, testable, and runnable with
no networking code. The network layer may import consensus modules; consensus
modules must never import the network layer.

## Consequences

- All block, header, transaction, and state validation remains in the existing
  Protocol V2 modules.
- A malicious or offline peer cannot change local canonical state.
- The network layer is free to evolve (new message types, transports,
  encryption) without risk of changing consensus.
- Future light-client protocols must also respect this boundary.

## Status

Accepted as part of Phase 8A.
