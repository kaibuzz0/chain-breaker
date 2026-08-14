# CONSENSUS-CRITICAL: Protocol V2 network identity and genesis derivation.

# Changes require review per docs/CONSENSUS_CHANGE_POLICY.md.



"""Network identity and deterministic genesis derivation for Protocol V2.



A Protocol V2 network is identified by:



  - a unique ``network_id`` string

  - a genesis block header that commits to the bootstrap registry root

  - the bootstrap governance key set and threshold used to derive that root



The existing ``chainbreaker-scripture-v2`` alpha identity is frozen and remains

the historical legacy/dev/test identity.  Any production deployment must create a

*new* network identity via an explicit key ceremony.  Reinterpreting an existing

chain under a different identity is rejected.

"""



from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .block import (
    GENESIS_GOVERNANCE_KEYS,
    GENESIS_HASH,
    GENESIS_HEADER_BYTES,
    GENESIS_REGISTRY_ROOT,
    MAX_TARGET,
    NETWORK_ID,
    PROTOCOL_VERSION,
    BlockHeaderV2,
    BlockV2,
    mine_header_v2,
)
from .registry_state import RegistryState, registry_root


class NetworkIdentityError(ValueError):

    """Raised when a network identity is invalid or cannot be satisfied."""





ALPHA_NETWORK_KINDS: set[str] = {"alpha", "dev", "test"}

PRODUCTION_NETWORK_KINDS: set[str] = {"production"}

VALID_NETWORK_KINDS: set[str] = ALPHA_NETWORK_KINDS | PRODUCTION_NETWORK_KINDS





@dataclass(frozen=True)

class NetworkIdentity:

    """Immutable description of a Protocol V2 network identity.



    Attributes:

        network_id: unique human-readable identifier for this network.

        kind: one of ``alpha``, ``dev``, ``test``, or ``production``.

        genesis_hash: expected hash of the canonical genesis block.

        genesis_registry_root: registry root committed by the genesis header.

        governance_keys: bootstrap governance public key hexes (sorted).

        governance_threshold: required signatures from ``governance_keys``.

        genesis_header_bytes: serialized canonical genesis header.

        genesis_timestamp: Unix seconds baked into the genesis header.

    """



    network_id: str

    kind: str

    genesis_hash: str

    genesis_registry_root: str

    governance_keys: tuple[str, ...]

    governance_threshold: int

    genesis_header_bytes: bytes

    genesis_timestamp: int = 1704067200



    def to_dict(self) -> dict[str, Any]:

        """Return a JSON-serializable representation."""

        return {

            "network_id": self.network_id,

            "kind": self.kind,

            "genesis_hash": self.genesis_hash,

            "genesis_registry_root": self.genesis_registry_root,

            "governance_keys": list(self.governance_keys),

            "governance_threshold": self.governance_threshold,

            "genesis_header_bytes_hex": self.genesis_header_bytes.hex(),

            "genesis_timestamp": self.genesis_timestamp,

        }



    @classmethod

    def from_dict(cls, data: dict[str, Any]) -> NetworkIdentity:

        """Reconstruct an identity from its JSON representation."""

        keys = tuple(str(k) for k in data["governance_keys"])

        raw_bytes = data.get("genesis_header_bytes_hex") or data.get("genesis_header_bytes")

        return cls(

            network_id=str(data["network_id"]),

            kind=str(data["kind"]),

            genesis_hash=str(data["genesis_hash"]),

            genesis_registry_root=str(data["genesis_registry_root"]),

            governance_keys=keys,

            governance_threshold=int(data["governance_threshold"]),

            genesis_header_bytes=bytes.fromhex(str(raw_bytes)),

            genesis_timestamp=int(data.get("genesis_timestamp", 1704067200)),

        )



    def is_alpha(self) -> bool:

        """Return True if this is the frozen legacy alpha identity."""

        return self.kind == "alpha"



    def is_dev_test(self) -> bool:

        """Return True if this is an explicit dev/test identity."""

        return self.kind in ("dev", "test")



    def is_production(self) -> bool:

        """Return True if this is a production identity."""

        return self.kind in PRODUCTION_NETWORK_KINDS





def alpha_network_identity() -> NetworkIdentity:

    """Return the frozen Protocol V2 alpha/dev/test network identity.



    This identity uses the immutable genesis constants shipped with the alpha

    release.  It is the only identity that may use the placeholder governance

    key set.

    """

    return NetworkIdentity(

        network_id=NETWORK_ID,

        kind="alpha",

        genesis_hash=GENESIS_HASH,

        genesis_registry_root=GENESIS_REGISTRY_ROOT,

        governance_keys=tuple(GENESIS_GOVERNANCE_KEYS),

        governance_threshold=2,

        genesis_header_bytes=GENESIS_HEADER_BYTES,

        genesis_timestamp=1704067200,

    )





def _validate_governance_keys_for_identity(

    governance_keys: list[str],

    threshold: int,

    *,

    allow_placeholder_keys: bool,

) -> tuple[tuple[str, ...], str]:

    """Validate and canonicalize governance keys.



    Returns ``(sorted_keys, registry_root)`` for the resulting genesis state.

    Raises NetworkIdentityError on invalid input.

    """

    if not isinstance(governance_keys, list) or len(governance_keys) == 0:

        raise NetworkIdentityError("governance_keys must be a non-empty list")

    if not (1 <= threshold <= len(governance_keys)):

        raise NetworkIdentityError(

            f"governance_threshold must satisfy 1 <= threshold <= {len(governance_keys)}"

        )

    for key in governance_keys:

        if not isinstance(key, str) or len(key) != 64:

            raise NetworkIdentityError(

                f"governance key must be a 64-character lowercase hex string: {key!r}"

            )

        try:

            int(key, 16)

        except ValueError as exc:

            raise NetworkIdentityError(f"governance key is not valid hex: {key!r}") from exc

        if key != key.lower():

            raise NetworkIdentityError(f"governance key must be lowercase hex: {key!r}")



    sorted_keys = tuple(sorted(governance_keys))

    if not allow_placeholder_keys:

        placeholder = tuple(sorted(GENESIS_GOVERNANCE_KEYS))

        if sorted_keys == placeholder:

            raise NetworkIdentityError(

                "production identity cannot use the placeholder alpha governance key set"

            )

    return sorted_keys, registry_root(RegistryState.genesis(list(sorted_keys), threshold))





def derive_test_network_identity(

    governance_keys: list[str],

    governance_threshold: int,

    *,

    genesis_timestamp: int = 1704067200,

    max_mining_iterations: int = 10_000_000,

) -> NetworkIdentity:

    """Derive a deterministic test/dev network identity from a governance set.



    The network_id is derived from the resulting genesis registry root so that

    the same key ceremony always produces the same test network, while

    different key sets produce distinct networks.  This lets unit tests and

    operators create isolated V2 networks without picking a network_id by hand.

    """

    sorted_keys, _ = _validate_governance_keys_for_identity(

        governance_keys, governance_threshold, allow_placeholder_keys=False

    )

    temp_state = RegistryState(

        records=(),

        governance_version=1,

        network_id="__temp__",

        governance_keys=sorted_keys,

        threshold=governance_threshold,

    )

    root = registry_root(temp_state)

    network_id = f"chainbreaker-scripture-v2-test-{root[:16]}"

    return derive_network_identity(

        network_id=network_id,

        governance_keys=governance_keys,

        governance_threshold=governance_threshold,

        kind="test",

        genesis_timestamp=genesis_timestamp,

        max_mining_iterations=max_mining_iterations,

    )





def derive_network_identity(

    network_id: str,

    governance_keys: list[str],

    governance_threshold: int,

    *,

    kind: str = "production",

    genesis_timestamp: int = 1704067200,

    max_mining_iterations: int = 10_000_000,

) -> NetworkIdentity:

    """Derive a new deterministic Protocol V2 network identity from a key ceremony.



    The resulting identity has its own genesis block, genesis hash, and registry

    root.  It is *not* the alpha chain; it is a new V2 network instance.



    Raises NetworkIdentityError if mining fails or the key configuration is

    invalid.

    """

    if kind not in VALID_NETWORK_KINDS:

        raise NetworkIdentityError(f"unsupported network kind: {kind!r}")

    allow_placeholder = kind in ALPHA_NETWORK_KINDS

    sorted_keys, derived_registry_root = _validate_governance_keys_for_identity(

        governance_keys, governance_threshold, allow_placeholder_keys=allow_placeholder

    )



    # Network ID is part of the registry state serialization, so changing it

    # changes the registry root.  Compute the genesis state with the requested ID.

    genesis_state = RegistryState(

        records=(),

        governance_version=1,

        network_id=network_id,

        governance_keys=sorted_keys,

        threshold=governance_threshold,

    )

    derived_registry_root = registry_root(genesis_state)



    header = BlockHeaderV2(

        version=PROTOCOL_VERSION,

        prev_hash="0" * 64,

        merkle_root="0" * 64,

        registry_root=derived_registry_root,

        timestamp=genesis_timestamp,

        target=MAX_TARGET,

        nonce=0,

    )

    if not mine_header_v2(header, max_iterations=max_mining_iterations, start_nonce=0):

        raise NetworkIdentityError(

            f"failed to mine genesis header for network {network_id!r} within iteration limit"

        )



    genesis_block = BlockV2(header=header, transactions=[])

    return NetworkIdentity(

        network_id=network_id,

        kind=kind,

        genesis_hash=genesis_block.hash,

        genesis_registry_root=derived_registry_root,

        governance_keys=sorted_keys,

        governance_threshold=governance_threshold,

        genesis_header_bytes=header_bytes_for(header),

        genesis_timestamp=genesis_timestamp,

    )





def genesis_block_for(identity: NetworkIdentity) -> BlockV2:

    """Return the genesis BlockV2 for the given network identity.



    The block is reconstructed from the identity's canonical header bytes and

    carries zero transactions, matching the Protocol V2 genesis model.

    """

    from .codec import BinaryCodec

    header_dict, _ = BinaryCodec.decode_header_v2(identity.genesis_header_bytes)

    return BlockV2(header=BlockHeaderV2.from_dict(header_dict), transactions=[])





def header_bytes_for(header: BlockHeaderV2) -> bytes:

    """Return the canonical serialized bytes for a v2 header."""

    from .codec import BinaryCodec

    return BinaryCodec.encode_header_v2(header.to_dict())





def identity_matches_genesis(identity: NetworkIdentity, block: BlockV2 | None) -> bool:

    """Return True if ``block`` is the genesis block for ``identity``."""

    if block is None:

        return False

    if block.header.prev_hash != "0" * 64:

        return False

    if block.header.version != PROTOCOL_VERSION:

        return False

    if block.hash != identity.genesis_hash:

        return False

    expected_bytes = identity.genesis_header_bytes

    try:

        from .codec import BinaryCodec

        actual = BinaryCodec.encode_header_v2(block.header.to_dict())

    except Exception:

        return False

    return actual == expected_bytes
