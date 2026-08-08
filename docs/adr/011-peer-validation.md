---
number: 011
title: Peers Are Untrusted Data Sources
date: 2026-08-08
status: accepted
---

# ADR 011 — Peer Validation

## Context

A networked ledger receives data from arbitrary peers. Any peer may be honest,
broken, or hostile. If the node trusts peer metadata (height, work, version), it
becomes vulnerable to eclipse and Sybil attacks.

## Decision

Peers are **untrusted data sources**. Every byte received from a peer is
validated independently against local Protocol V2 rules and constants.

Peer metadata (`best_height`, `best_chain_work`, `feature_bits`, limits) is
advisory only. It may guide sync priority, but it may never override local
validation.

## Consequences

- Handshake rejects peers with wrong genesis, network ID, or protocol version.
- Sync computes accumulated work locally.
- Reorgs use the same `ReorgEngine` for network-proposed and locally-mined
  blocks.
- No peer has authority to declare a chain canonical.

## Status

Accepted as part of Phase 8A.
