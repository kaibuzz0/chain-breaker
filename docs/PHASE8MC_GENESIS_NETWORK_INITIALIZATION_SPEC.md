# Phase 8M-C: Genesis & Network Initialization



## Goal



Make the distinction between the frozen Protocol V2 alpha/dev/test identity and

any production network identity explicit, unambiguous, and enforced by code.



## Background



Protocol V2 shipped with a single frozen genesis block:



| Constant | Value |

|---|---|

| `NETWORK_ID` | `chainbreaker-scripture-v2` |

| `GENESIS_HASH` | `0000a6fd1e57aafd19da552440faa94803dbf1a1773bcd9af8ce3e0ae9fd13db` |

| `GENESIS_REGISTRY_ROOT` | `5814321ad489e630fef0350b1bff591d5cee8a821c00fa40a2cb2c99bd5b3186` |

| `GENESIS_HEADER_BYTES` | frozen canonical header bytes |



That genesis header commits to a specific registry root, and that registry root

is the hash of a registry state that includes the placeholder governance key set

and threshold.  Because the genesis header commits to the governance set, a

different governance set necessarily produces a different registry root,

therefore a different genesis block, therefore a different network identity.



Phase 8M-C codifies this: the existing alpha identity stays immutable; any

production deployment creates a *new* V2 network instance.



## Design



### Network identity object



`chainbreaker.network_identity.NetworkIdentity` is an immutable description of a

Protocol V2 network:



- `network_id`: unique human-readable identifier.

- `kind`: `alpha`, `dev`, `test`, or `production`.

- `genesis_hash`: expected hash of the genesis block.

- `genesis_registry_root`: registry root committed by the genesis header.

- `governance_keys`: bootstrap governance public keys (sorted, 64-char hex).

- `governance_threshold`: required signatures from the bootstrap set.

- `genesis_header_bytes`: canonical serialized genesis header.



Two primary constructors are provided:



- `alpha_network_identity()` — returns the frozen alpha identity.

- `derive_network_identity(...)` — derives a new deterministic identity from a

  key ceremony (production or explicit test/dev).

- `derive_test_network_identity(...)` — derives an isolated test identity with a

  deterministic network_id derived from the governance root.



### Rules enforced



1. **The alpha identity is immutable.**

   `GENESIS_HEADER_BYTES`, `GENESIS_HASH`, `GENESIS_REGISTRY_ROOT`, and

   `NETWORK_ID` must not change.



2. **Only the alpha identity may use the placeholder governance keys.**

   The keys `0000...`, `1111...`, `2222...` are valid only inside the alpha

   network identity.



3. **No reinterpretation of existing chains.**

   `Ledger.from_dict()` verifies that the stored genesis block, stored network

   identity, and stored governance keys describe one consistent identity.  A

   mismatch is a hard error.



4. **Configured identity must reproduce the genesis registry root.**

   When a ledger is loaded or created, the registry state derived from the

   configured governance keys and network_id must hash to the registry root in

   the genesis header.



5. **Production requires an explicit key ceremony.**

   `hon v2 chain init --network-id prod --governance-key gov_0.hex ...` derives

   a new identity from the supplied private key files.  No implicit fallback to

   placeholder keys exists.



6. **No generic network override.**

   There is no `--override-network` flag.  If an operator wants a different

   network, they initialize it as a different network with its own genesis.



7. **Genesis cannot be re-mined.**

   `mine_header_v2()` rejects any attempt to re-mine a header whose canonical

   bytes equal `GENESIS_HEADER_BYTES`.



8. **Dead genesis model removed.**

   `_compute_genesis_constants()` was removed from the consensus runtime.



## CLI changes



`hon v2 chain init` now supports:



```bash

# Frozen alpha identity (default, implicit)

hon v2 chain init -o ledger.json



# Explicit alpha/dev/test identity

hon v2 chain init -o ledger.json --dev



# Production/test network from a key ceremony

hon v2 chain init -o ledger.json \

    --network-id my-production-v2 \

    --governance-key gov_0.hex \

    --governance-key gov_1.hex \

    --governance-key gov_2.hex \

    --governance-threshold 2

```



Omitting `--governance-key` while requesting a custom `--network-id` is an

error.



## Library changes



- `chainbreaker/network_identity.py` — new module.

- `chainbreaker/block.py` — removed dead `_compute_genesis_constants()`;

  hardened `mine_header_v2()` genesis guard.

- `chainbreaker/chain.py` — `Ledger` carries a `NetworkIdentity`; validates it

  on construction and deserialization; auto-derives a test identity when real

  governance keys are supplied without an explicit identity (backward-compatible

  test behaviour).

- `chainbreaker/cli_v2.py` — `v2 chain init` supports production and dev

  modes; `_load_ledger` validates network identity instead of hardcoding

  `NETWORK_ID`.

- `chainbreaker/reorg.py` — `ReorgEngine` infers a consistent identity for

  internal target computation.

- `chainbreaker/registry_state.py` — added `RegistryState.with_network_id()`.



## Migration notes



Existing alpha ledgers created before this phase load without modification

because `Ledger.from_dict()` defaults to the alpha identity when

`network_identity` is absent.  The legacy serialization gains a

`network_identity` field on the next save.



Any project that previously instantiated `Ledger(governance_keys=...)` to

create an isolated test chain now receives a deterministic `test` network

identity instead of silently reusing the alpha genesis with mismatched keys.

This is a behavioural change, but it fixes a silent identity bug.



## Verification



Regression tests live in

`tests/test_phase8mc_genesis_network_initialization.py` and cover:



- alpha identity stability and immutability

- alpha genesis cannot be re-mined

- rejection of mismatched governance keys / network_id / genesis hash on load

- production identity distinctness and determinism

- production identity rejects placeholder keys

- production ledger mines and validates

- CLI enforces explicit key ceremony for production

- no override can silently reinterpret historical state
