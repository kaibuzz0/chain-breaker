# Consensus Freeze — v2.0.0-alpha

## Frozen rules

1. **Header v2 fields** and their canonical encoding order.
2. **Genesis block** construction and registry-root commitment.
3. **Proof-of-work** target and deterministic difficulty behavior.
4. **Registry governance reducer** state transitions for `register`, `rotate`, `revoke`.
5. **Attestation validation** using curator signatures over canonical headers.
6. **Chain selection** — currently longest valid chain; subject to change when reorg engine lands.

## What is not frozen

- Storage format and backend interface.
- Network message framing and peer protocol.
- Reorganization / fork-choice behavior.
- CLI presentation and help text (except command names and argument semantics).

## Changing frozen rules

Any change requires:
- A new protocol version header.
- A migration path for existing chains.
- Updated release package under `docs/releases/`.
