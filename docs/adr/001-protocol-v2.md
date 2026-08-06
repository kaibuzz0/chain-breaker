# ADR 001 — Protocol v2 Canonical Block Format

## Status

Accepted — frozen at v2.0.0-alpha.

## Context

Chain-Breaker needs an unambiguous, deterministic serialization format so that:

1. Any two correct implementations produce the same block hash from the same logical block.
2. Historical attestations remain verifiable forever without a reference implementation.
3. Cross-platform CI yields identical hashes across Python versions and operating systems.

## Decision

Protocol v2 uses a flat, ordered, length-prefixed canonical encoding:

- Every header field is serialized in a fixed order.
- All integers are big-endian unsigned fixed-width.
- All byte sequences are length-prefixed with a 4-byte big-endian length.
- No implicit padding, no variable-length integers, no platform-dependent types.

The block hash is `SHA-256(canonical(header_bytes))`.

## Rationale

Canonical serialization removes a common source of consensus failure: two implementations disagreeing on how to encode the same data. A flat format is easier to audit, easier to implement in other languages, and easier to fuzz.

## Alternatives considered

| Approach | Rejected because |
|----------|------------------|
| JSON | Non-deterministic key ordering and number encoding. |
| CBOR | Multiple valid encodings for the same value; dependency risk. |
| Protobuf | Field presence and default-value rules vary by implementation. |
| Custom TLV | Harder to parse safely; more code surface for bugs. |

## Invariants that must never change

1. Field order in Header v2 is fixed.
2. Hash algorithm is SHA-256.
3. Length prefix width is 4 bytes, big-endian unsigned.
4. `prev_hash` of the genesis block is 32 zero bytes.

## Extension points

- Protocol v3 may introduce a new header version byte and new field schema.
- A v2 block remains valid forever under the v2 rules.

## Compatibility implications

- Changing any invariant requires a new ADR and a protocol version bump.
- Old clients must continue to validate v2 blocks unchanged.
