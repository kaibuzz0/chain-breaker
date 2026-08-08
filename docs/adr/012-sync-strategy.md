---
number: 012
title: Synchronization Follows Headers → Blocks → State → Archive Order
date: 2026-08-08
status: accepted
---

# ADR 012 — Sync Strategy

## Context

A node joining the network must catch up to the current canonical chain. It
must do so safely: it cannot trust peers to tell it which chain is best, and it
cannot download arbitrary state blobs that bypass validation.

## Decision

Synchronization follows a strict order:

```
headers
   |
   v
blocks
   |
   v
state verification (local replay)
   |
   v
archive objects (lazy)
```

Headers are downloaded first to determine accumulated work. Full blocks are
downloaded only for the chain with the most work. State is recomputed locally
from blocks. Archive objects are fetched lazily by content hash.

## Consequences

- No state blob from a peer is ever trusted.
- A node always validates the full header chain before requesting blocks.
- Lazy archive sync minimizes bandwidth for nodes that do not need every
  manuscript object.

## Status

Accepted as part of Phase 8A.
