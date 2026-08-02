# Fork Divergence Adversarial Review

Phase: **5D  Fork and Chain Divergence Simulation**  
Branch: `registry-governance-hardening`  
Starting HEAD: `7050ab07512ac14dde6e14834709968082f0be20`

## Goal

Verify that competing valid histories maintain independent deterministic state.

## Scope

Local simulation only. No P2P, no networking, no peer discovery, no production
synchronization, no full reorganization engine.

## Test plan

1. Fork creation: two branches share genesis and block 1, then diverge.
2. Registry divergence: branch A registers curator A, branch B registers curator B.
3. Branch replay: selecting a history determines state; old branch state is not reused.
4. Cache isolation: corrupted cache on one ledger does not affect another.
5. Common ancestor: shared ancestor state matches; branches diverge only after fork point.
6. Chain-work selection: higher-work valid chain preferred; invalid chain rejected.
7. Malicious fork cases: invalid registry root, governance, witness, previous hash, state.

## Findings

(To be filled as issues are discovered.)
