# Corruption Adversarial Review

Phase: **5E  Corruption Testing**  
Branch: `registry-governance-hardening`  
Starting HEAD: `0baf6a8`

## Goal

Verify that corrupted or malicious data is rejected safely, without partial state
updates, cache mutation, or crashes.

## Scope

Local data corruption only. No P2P, no networking, no production recovery, no
new protocol features.

## Test plan

1. Block corruption: modified header fields, truncated/extra bytes.
2. Registry state corruption: altered governance keys, threshold, records, cached states.
3. Governance transaction corruption: modified signatures/fields, missing fields, invalid values.
4. Witness corruption: modified signatures, wrong IDs/heights, malformed keys.
5. Serialization corruption: random byte mutations, truncation, appended garbage, invalid lengths.
6. Failure safety: invalid data must not update state or cache.

## Findings

(To be filled as issues are discovered.)
