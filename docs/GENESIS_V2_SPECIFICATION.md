# Genesis v2 Specification



Version: `chainbreaker-scripture-v2`

Status: **implemented and frozen at v2.0.0-alpha**



> ⚠️ **Network identity distinction (Phase 8M-C).** The genesis described below is the **alpha/dev/test legacy identity** for Protocol V2. A production deployment must create a **new, distinct network identity** with its own key ceremony; it must not reuse these frozen constants with a different governance set. See `PHASE8MC_GENESIS_NETWORK_INITIALIZATION_SPEC.md`.



This document defines the exact genesis block and registry state for the

Chain-Breaker v2 network.  The genesis block is the constitutional root of the

ledger; every validating node must reproduce it exactly from the constants in

this specification.



---



## 1. Genesis as a constant, not a function



The genesis block is a **fixed protocol constant**.  It is not computed at

runtime during normal chain validation.



The codebase must contain hard-coded values for:



```text

GENESIS_HEADER_BYTES

GENESIS_HASH

GENESIS_REGISTRY_ROOT

```



A separate **generator tool** may be used to discover the nonce and produce

these constants, but once the specification is finalized the generator output

is treated as immutable.



Every node must verify genesis by:



```text

assert encode_header_v2(GENESIS_HEADER) == GENESIS_HEADER_BYTES

assert header_hash(GENESIS_HEADER) == GENESIS_HASH

assert genesis_header.registry_root == GENESIS_REGISTRY_ROOT

assert satisfies_pow(GENESIS_HASH, GENESIS_TARGET)

```



---



## 2. Network constants



```text

PROTOCOL_VERSION = 2

NETWORK_ID = "chainbreaker-scripture-v2"

GENESIS_MESSAGE = "Chain-Breaker v2 Genesis: ledger-derived curator governance"

GENESIS_TIMESTAMP = 1704067200

GENESIS_TARGET = MAX_TARGET

GENESIS_TYPE_MARKER = 0x02

GENESIS_MERKLE_ROOT = "0000000000000000000000000000000000000000000000000000000000000000"

GENESIS_PREV_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

```



Package version: `0.3.0`.



---



## 3. Genesis governance key set



The genesis registry state includes the initial governance key set and

threshold.  These are protocol constants.



For this alpha/devnet genesis, the key set is a **deterministic placeholder**.

A production network must replace these placeholders with real Ed25519 public

keys generated through an independent, documented ceremony.



### Placeholder keys



```text

GENESIS_GOVERNANCE_KEY_1 = "0000000000000000000000000000000000000000000000000000000000000000"

GENESIS_GOVERNANCE_KEY_2 = "1111111111111111111111111111111111111111111111111111111111111111"

GENESIS_GOVERNANCE_KEY_3 = "2222222222222222222222222222222222222222222222222222222222222222"

GENESIS_GOVERNANCE_KEYS = [KEY_1, KEY_2, KEY_3]  # sorted lexicographically

GENESIS_THRESHOLD = 2

```



### Ordering rule



Governance keys are sorted lexicographically by their lowercase hex string

before being placed in the registry state.  This ensures canonical serialization

across independent implementations.



### Threshold rule



```text

1 <= threshold <= len(governance_keys)

```



The genesis threshold must require more than one signature if there is more

than one key.  A threshold of `0` or a threshold greater than the number of

keys is invalid.



---



## 4. Genesis registry state



The genesis registry state is:



```text

RegistryState(

    governance_version = 1,

    network_id = "chainbreaker-scripture-v2",

    governance_keys = [

        "0000000000000000000000000000000000000000000000000000000000000000",

        "1111111111111111111111111111111111111111111111111111111111111111",

        "2222222222222222222222222222222222222222222222222222222222222222",

    ],

    threshold = 2,

    curators = [],

)

```



### Registry root



```text

GENESIS_REGISTRY_ROOT = registry_root(genesis_registry_state)

```



The root is computed from the canonical serialization of the state described

above.  It is a fixed 64-character hex string.



### Important: genesis state is the state *at height 0*



The genesis block contains no transactions, so the registry state at the end

of block 0 equals the genesis registry state.  The genesis header's

`registry_root` commits to this state.



---



## 5. Genesis header fields



```text

version       = 2

prev_hash     = "0000000000000000000000000000000000000000000000000000000000000000"

merkle_root   = "0000000000000000000000000000000000000000000000000000000000000000"

registry_root = GENESIS_REGISTRY_ROOT

timestamp     = 1704067200

target        = "0000ffff00000000000000000000000000000000000000000000000000000000"

nonce         = <computed by brute force>

```



### Header dictionary



```python

genesis_header = {

    "version": 2,

    "prev_hash": "0" * 64,

    "merkle_root": "0" * 64,

    "registry_root": GENESIS_REGISTRY_ROOT,

    "timestamp": 1704067200,

    "target": "0000ffff00000000000000000000000000000000000000000000000000000000",

    "nonce": GENESIS_NONCE,

}

```



### Canonical bytes



```text

GENESIS_HEADER_BYTES = BinaryCodec.encode_header_v2(genesis_header)

```



This must be exactly 149 bytes.



### Genesis hash



```text

GENESIS_HASH = SHA-256(SHA-256(GENESIS_HEADER_BYTES))

```



The genesis hash must satisfy:



```text

int(GENESIS_HASH, 16) <= int(GENESIS_TARGET, 16)

```



---



## 6. Genesis verification invariants



A node must be able to verify the genesis block independently:



```text

1. len(GENESIS_HEADER_BYTES) == 149

2. decode_header_v2(GENESIS_HEADER_BYTES) succeeds and returns offset 149

3. decoded header fields match the genesis constants

4. header_hash(decoded header) == GENESIS_HASH

5. satisfies_pow(GENESIS_HASH, GENESIS_TARGET)

6. decoded registry_root == registry_root(RegistryState.genesis(...))

7. decoded version == 2

8. decoded type marker == 0x02

```



Any violation means the node is running the wrong protocol or the genesis

constants have been corrupted.



---



## 7. Genesis registry state factory



The implementation must provide:



```python

RegistryState.genesis(

    governance_keys: list[str],

    threshold: int,

) -> RegistryState

```



Requirements:



- Sort `governance_keys` lexicographically.

- Validate `1 <= threshold <= len(governance_keys)`.

- Set `governance_version = 1`.

- Set `network_id = "chainbreaker-scripture-v2"`.

- Set `curators = []`.

- Return an immutable `RegistryState`.



This factory is used both for the genesis constants and for tests.



---



## 8. Open question before implementation



The placeholder governance keys above are all-zeros and all-same-pattern keys.

They are **not valid Ed25519 public keys** because Ed25519 requires the key to

be a valid point on the curve.



For the alpha/devnet genesis, this is acceptable because the keys are only used

inside `RegistryState` serialization and governance-signature validation will

fail with these placeholders until a real network replaces them.



However, two options exist:



### Option A: placeholder non-curve keys (current choice)



Pros:



- Genesis state root can be computed immediately for testing.

- No dependency on external key generation for the specification.



Cons:



- Real networks must replace the keys before launch.

- Governance signature tests cannot use the placeholder keys directly.



### Option B: real generated keys in the specification



Pros:



- Genesis state is immediately cryptographically valid.

- Test vectors can include real governance signatures from block 1.



Cons:



- Requires a documented key-generation ceremony before the spec is finalized.

- Changing the spec if the key generation changes is more disruptive.



Current recommendation: **Option A for the alpha/devnet spec**, with a clear

documentation note that a production network must create a **new, distinct

network identity** with a separate key ceremony.  Replacing the placeholders

while keeping `NETWORK_ID`, `GENESIS_HASH`, and `GENESIS_REGISTRY_ROOT` would

produce a chain whose genesis header commits to a different registry root,

breaking consensus.  See `PHASE8MC_GENESIS_NETWORK_INITIALIZATION_SPEC.md`.



---



## 9. Test vectors required



The implementation milestone must produce fixed vectors for:



1. Canonical serialization of the genesis registry state.

2. `GENESIS_REGISTRY_ROOT`.

3. `GENESIS_HEADER_BYTES` (149 bytes hex).

4. `GENESIS_HASH`.

5. `GENESIS_NONCE`.

6. Round-trip:

   ```text

   encode(decode(GENESIS_HEADER_BYTES)) == GENESIS_HEADER_BYTES

   ```

7. Verification of all genesis invariants in section 6.



These vectors must be computed in two independent fresh processes and must

match exactly.



---



## 10. Relationship to later milestones



Milestone 4B will implement this specification in code.  It must not:



- change the header layout

- change the registry state canonical serialization

- change the hash algorithm

- introduce dynamic genesis generation as the source of truth



Milestones 4C, 4D, and 4E must treat the genesis constants as immutable.



---



## 11. Governance authority chain



The complete authority chain from genesis onward is:



```text

Genesis block

    |

    +-- commits to RegistryState with genesis governance keys + threshold

            |

            +-- first curator_register transaction (height 1)

                    |

                    +-- signed by threshold genesis governance keys

                            |

                            +-- produces new RegistryState

                                    |

                                    +-- next governance transaction

                                            |

                                            +-- signed by threshold active keys

```



No governance action is valid without a chain of signatures rooted in the

genesis key set.
