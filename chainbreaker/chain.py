# CONSENSUS-CRITICAL: Protocol V2 consensus-sensitive code. Changes require review per docs/CONSENSUS_CHANGE_POLICY.md.



"""Ledger and chain validation with 256-bit target and retarget rules."""



from __future__ import annotations

import time
from typing import Any, Callable

from .block import (
    GENESIS_GOVERNANCE_KEYS,
    GENESIS_TARGET,
    GENESIS_THRESHOLD,
    MAX_TARGET,
    MIN_TARGET,
    NETWORK_ID,
    PROTOCOL_VERSION,
    Block,
    BlockHeader,
    BlockHeaderV2,
    BlockV2,
)
from .codec import BinaryCodec, validate_v2_transaction
from .crypto import HashEngine, MerkleTree, work_for_target, work_for_target_v2
from .governance import (
    CuratorRegisterTx,
    CuratorRevokeTx,
    CuratorRotateTx,
    GovernanceContext,
    GovernanceError,
)
from .network_identity import (
    NetworkIdentity,
    NetworkIdentityError,
    alpha_network_identity,
    derive_test_network_identity,
    identity_matches_genesis,
)
from .registry_state import (
    RegistryError,
    RegistryState,
    apply_registry_transaction,
    registry_root,
)

TARGET_BLOCK_TIME = 600

DIFFICULTY_RETARGET_INTERVAL = 10

MAX_RETARGET_FACTOR = 4









def _canonical_txid(body_dict: dict[str, Any]) -> str:

    """Return a deterministic transaction ID with canonical signature ordering."""

    canonical_body = dict(body_dict)

    if "governance_signatures" in canonical_body:

        canonical_body["governance_signatures"] = sorted(

            canonical_body["governance_signatures"],

            key=lambda s: int(s.get("key_index", 0)),

        )

    return HashEngine.hash_object_hex(canonical_body)





class LedgerError(ValueError):

    pass





class Ledger:

    """A proof-of-work ledger."""



    def __init__(self, chain: list[Block | BlockV2] | None = None,

                 transaction_validator: Callable[[dict[str, Any]], bool] | None = None,

                 max_block_size: int = 1_000_000,

                 max_transactions: int = 10_000,

                 network_id: str | None = None,

                 governance_keys: list[str] | None = None,

                 governance_threshold: int | None = None,

                 network_identity: NetworkIdentity | None = None,

                 _strict_identity: bool = True):

        if network_identity is None:

            if governance_keys is None or sorted(governance_keys) == sorted(GENESIS_GOVERNANCE_KEYS):

                network_identity = alpha_network_identity()

            else:

                threshold = governance_threshold if governance_threshold is not None else GENESIS_THRESHOLD

                network_identity = derive_test_network_identity(governance_keys, threshold)

        if chain is None:

            from .network_identity import genesis_block_for

            chain = [genesis_block_for(network_identity)]

        self.chain = list(chain)

        self.network_identity = network_identity

        self.network_id = network_identity.network_id

        self.transaction_validator = transaction_validator

        self.max_block_size = max_block_size

        self.max_transactions = max_transactions

        self.governance_keys = list(governance_keys or network_identity.governance_keys)

        self.governance_threshold = governance_threshold if governance_threshold is not None else network_identity.governance_threshold

        self._governance_context = GovernanceContext(self.governance_keys, self.governance_threshold)

        self.registry_states: dict[int, RegistryState] = {}

        self._governance_keys = list(self.governance_keys)

        self._governance_threshold = self.governance_threshold

        # Ensure the genesis block's registry root matches the configured identity.

        if _strict_identity:

            self._validate_genesis_identity()

        if isinstance(self.chain[0], BlockV2):

            self._replay_registry_states()

        else:

            self.registry_states[0] = RegistryState.genesis(self.governance_keys, self.governance_threshold)

            self._replay_registry_states()



    def _validate_genesis_identity(self) -> None:

        """Verify the genesis block belongs to this ledger's network identity.



        Raises NetworkIdentityError if the stored genesis block, configured

        governance keys, and configured network ID do not describe a single

        consistent identity.

        """

        if not self.chain:

            raise NetworkIdentityError("ledger chain is empty")

        genesis = self.chain[0]

        identity = self.network_identity



        if not identity_matches_genesis(identity, genesis if isinstance(genesis, BlockV2) else None):

            raise NetworkIdentityError(

                f"genesis block does not match network identity {identity.network_id!r}"

            )



        # Replay the genesis registry state and confirm it reproduces the root

        # committed by the genesis header.  This guarantees the configured

        # governance set and network ID are exactly the ones that produced the

        # genesis header's registry_root.

        if isinstance(genesis, BlockV2):

            expected_root = identity.genesis_registry_root

            genesis_state = RegistryState.genesis(self.governance_keys, self.governance_threshold)

            # The alpha identity's network_id is baked into the registry state

            # serialization, but the new network_identity system stores it on the

            # identity object.  For historical alpha ledgers, the registry state

            # itself uses NETWORK_ID from governance.py; for new identities the

            # state must use the identity's network_id.

            if self.network_id != NETWORK_ID:

                genesis_state = genesis_state.with_network_id(self.network_id)

            actual_root = registry_root(genesis_state)

            if actual_root != expected_root:

                raise NetworkIdentityError(

                    f"genesis registry root mismatch for {self.network_id!r}: "

                    f"computed {actual_root} != expected {expected_root}"

                )



        # Only the frozen alpha identity may use the placeholder keys.

        if not identity.is_alpha():

            placeholder = tuple(sorted(GENESIS_GOVERNANCE_KEYS))

            if tuple(sorted(self.governance_keys)) == placeholder:

                raise NetworkIdentityError(

                    "only the alpha identity may use the placeholder governance keys"

                )



    def _replay_registry_states(self) -> None:

        """Recompute registry_states from genesis using only the chain.



        This is the deterministic replay path.  It is called on __init__ and

        may be called after a reorg in a future milestone.

        """

        genesis_state = RegistryState.genesis(self.governance_keys, self.governance_threshold)

        if self.network_id != NETWORK_ID:

            genesis_state = genesis_state.with_network_id(self.network_id)

        self.registry_states = {0: genesis_state}

        for height in range(1, len(self.chain)):

            self.registry_states[height] = self._apply_transactions(

                self.registry_states[height - 1],

                self.chain[height].transactions,

                height,

            )



    def _state_at(self, height: int) -> RegistryState:

        """Return the registry state at the given height by replaying the chain.



        This is the authoritative path.  It recomputes from genesis so that

        cached state can never be trusted as authoritative.

        """

        if height < 0 or height >= len(self.chain):

            raise LedgerError(f"invalid height {height} for state lookup")

        state = RegistryState.genesis(self.governance_keys, self.governance_threshold)

        if self.network_id != NETWORK_ID:

            state = state.with_network_id(self.network_id)

        for h in range(1, height + 1):

            state = self._apply_transactions(state, self.chain[h].transactions, h)

        return state



    def _apply_transactions(self, state: RegistryState, transactions: list[dict[str, Any]], height: int) -> RegistryState:

        """Fold governance transactions into a scratch state copy."""

        new_state = state

        for tx in transactions:

            parsed = self._parse_governance_transaction(tx)

            if parsed is not None:

                txid = _canonical_txid(parsed.to_dict())

                new_state = apply_registry_transaction(new_state, parsed, height, txid, self._governance_context)

        return new_state



    def _parse_governance_transaction(self, tx: dict[str, Any]) -> CuratorRegisterTx | CuratorRotateTx | CuratorRevokeTx | None:

        """Return a governance transaction object if tx is a registry mutation."""

        if not isinstance(tx, dict) or tx.get("type") != "governance":

            return None

        body = tx.get("body", {})

        action = body.get("action")

        if action == "curator_register":

            return CuratorRegisterTx.from_dict(body)

        if action == "curator_rotate":

            return CuratorRotateTx.from_dict(body)

        if action == "curator_revoke":

            return CuratorRevokeTx.from_dict(body)

        return None



    def registry_state_at(self, height: int) -> RegistryState:

        """Return the registry state after the block at the given height."""

        if height not in self.registry_states:

            raise LedgerError(f"registry state not available at height {height}")

        return self.registry_states[height]



    @property

    def last_block(self) -> Block | BlockV2:

        return self.chain[-1]



    def height(self) -> int:

        return len(self.chain) - 1



    def genesis_hash(self) -> str:

        return self.chain[0].hash



    def median_past_time(self, end: int, count: int = 11) -> int:

        """Median timestamp of the previous `count` blocks ending at `end`."""

        end = min(end, len(self.chain))

        start = max(0, end - count)

        if start >= end:

            return 0

        timestamps = sorted(self.chain[i].header.timestamp for i in range(start, end))

        return timestamps[(len(timestamps) - 1) // 2]



    def next_block_timestamp(self) -> int:

        """Choose a timestamp valid under the median-past rule."""

        last_ts = self.last_block.header.timestamp

        median = self.median_past_time(len(self.chain))

        now = int(time.time())

        return max(

            now,

            last_ts + 1,

            median + 1,

        )



    def expected_target_at(self, height: int) -> int:

        """Pure function: expected proof-of-work target at a given height."""

        if height <= 0:

            return GENESIS_TARGET

        if height < DIFFICULTY_RETARGET_INTERVAL:

            return self.chain[0].header.target

        if height % DIFFICULTY_RETARGET_INTERVAL != 0:

            return self.chain[height - 1].header.target

        return self.retarget(height)



    def retarget(self, height: int) -> int:

        """Calculate target at a retarget boundary.



        Uses the window of `DIFFICULTY_RETARGET_INTERVAL` blocks ending at

        `height - 1`, compared against the block immediately preceding the

        window. For the first retarget at height {DIFFICULTY_RETARGET_INTERVAL},

        the preceding block is the genesis block.

        """

        if height < DIFFICULTY_RETARGET_INTERVAL:

            return GENESIS_TARGET

        prev_index = height - DIFFICULTY_RETARGET_INTERVAL - 1

        first_block = self.chain[prev_index + 1]

        last_block = self.chain[height - 1]

        prev_target = self.chain[height - 1].header.target

        actual_time = last_block.header.timestamp - first_block.header.timestamp

        if actual_time <= 0:

            actual_time = 1

        expected_time = TARGET_BLOCK_TIME * DIFFICULTY_RETARGET_INTERVAL

        new_target = (prev_target * actual_time) // expected_time

        # Clamp to absolute bounds

        new_target = max(MIN_TARGET, min(MAX_TARGET, new_target))

        # Clamp to per-retarget factor-of-4 limits

        max_allowed = prev_target * MAX_RETARGET_FACTOR

        min_allowed = prev_target // MAX_RETARGET_FACTOR

        new_target = max(min_allowed, min(max_allowed, new_target))

        return new_target



    def mine_block(self,

                   transactions: list[dict[str, Any]],

                   max_iterations: int = 10_000_000,

                   coinbase: dict[str, Any] | None = None,

                   timestamp: int | None = None) -> Block | BlockV2:

        """Create and mine a new block."""

        if coinbase is not None:

            transactions = [coinbase] + list(transactions)



        for tx in transactions:

            validate_v2_transaction(tx)



        prev_hash = self.last_block.hash

        height = self.height() + 1

        target = self.expected_target_at(height)

        if timestamp is None:

            timestamp = self.next_block_timestamp()



        # Compute Merkle root

        tx_hashes = [HashEngine.hash_object(tx) for tx in transactions]

        merkle_root = MerkleTree(tx_hashes).root or bytes(32)

        merkle_root_hex = HashEngine.hex(merkle_root)



        header = BlockHeader(

            version=1,

            prev_hash=prev_hash,

            merkle_root=merkle_root_hex,

            timestamp=timestamp,

            target=target,

            nonce=0,

        )

        block = Block(header, list(transactions))

        if not block.mine(max_iterations=max_iterations):

            raise LedgerError("mining failed to find proof of work")

        return block



    def mine_block_v2(self,

                      transactions: list[dict[str, Any]],

                      max_iterations: int = 10_000_000,

                      timestamp: int | None = None) -> BlockV2:

        """Create and mine a new v2 block with registry-root commitment."""

        for tx in transactions:

            validate_v2_transaction(tx)



        prev_hash = self.last_block.hash

        height = self.height() + 1

        target = self.expected_target_at(height)

        if timestamp is None:

            timestamp = self.next_block_timestamp()



        previous_state = self._state_at(height - 1)

        registry_root_hex = registry_root(previous_state)



        tx_hashes = [HashEngine.hash_object(tx) for tx in transactions]

        merkle_root = MerkleTree(tx_hashes).root or bytes(32)

        merkle_root_hex = HashEngine.hex(merkle_root)



        header = BlockHeaderV2(

            version=2,

            prev_hash=prev_hash,

            merkle_root=merkle_root_hex,

            registry_root=registry_root_hex,

            timestamp=timestamp,

            target=target,

            nonce=0,

        )

        block = BlockV2(header=header, transactions=list(transactions))

        if not block.mine(max_iterations=max_iterations):

            raise LedgerError("mining failed to find proof of work")

        return block



    def add_block(self, block: Block | BlockV2) -> bool:

        """Validate and append a block to the chain."""

        if isinstance(block, BlockV2):

            return self.add_block_v2(block)

        return self._add_block_v1(block)



    def _add_block_v1(self, block: Block) -> bool:

        """Validate and append a v1 block to the chain (deprecated network)."""

        expected_height = self.height() + 1

        expected_target = self.expected_target_at(expected_height)

        expected_prev_hash = self.last_block.hash



        if block.header.prev_hash != expected_prev_hash:

            return False

        if block.header.target != expected_target:

            return False



        median = self.median_past_time(len(self.chain))

        now = int(time.time())



        if not block.verify(

            reference_time=now,

            median_past=median,

            expected_target=expected_target,

            transaction_validator=self.transaction_validator,

        ):

            return False



        self.chain.append(block)

        return True



    def add_block_v2(self, block: BlockV2) -> bool:

        """Validate and append a v2 block with registry-root commitment."""

        expected_height = self.height() + 1

        expected_target = self.expected_target_at(expected_height)

        expected_prev_hash = self.last_block.hash



        # Structural checks

        if block.header.prev_hash != expected_prev_hash:

            return False

        if block.header.target != expected_target:

            return False

        if not isinstance(block.header, BlockHeaderV2):

            return False

        if block.header.version != PROTOCOL_VERSION:

            return False



        # Registry-root commitment to previous state (replayed, not cached)

        previous_state = self._state_at(expected_height - 1)

        expected_registry_root = registry_root(previous_state)

        if block.header.registry_root != expected_registry_root:

            return False



        median = self.median_past_time(len(self.chain))

        now = int(time.time())



        if not block.verify(

            reference_time=now,

            median_past=median,

            expected_target=expected_target,

            transaction_validator=self.transaction_validator,

        ):

            return False



        # Apply governance transactions to produce the next state

        try:

            new_state = self._apply_transactions(previous_state, block.transactions, expected_height)

        except (RegistryError, GovernanceError):

            return False

        self.chain.append(block)

        self.registry_states[expected_height] = new_state

        return True



    def validate_chain(self, *, from_height: int = 0) -> bool:

        """Full validation of the chain from genesis up."""

        if not self.chain:

            return False

        genesis = self.chain[0]

        if not identity_matches_genesis(self.network_identity, genesis if isinstance(genesis, BlockV2) else None):

            return False

        if not genesis.verify(allow_genesis=True):

            return False



        for i in range(1, len(self.chain)):

            current = self.chain[i]

            previous = self.chain[i - 1]



            # Previous hash links to recomputed hash

            if current.header.prev_hash != previous.hash:

                return False



            # Difficulty

            expected_target = self.expected_target_at(i)

            if current.header.target != expected_target:

                return False



            # Median-past rule

            median = self.median_past_time(i)

            if current.header.timestamp <= median:

                return False



            # PoW and Merkle

            if not current.verify(

                median_past=median,

                expected_target=expected_target,

                transaction_validator=self.transaction_validator,

            ):

                return False



            # Registry-root commitment for v2 blocks

            if isinstance(current, BlockV2):

                previous_state = self._state_at(i - 1)

                expected_root = registry_root(previous_state)

                if current.header.registry_root != expected_root:

                    return False

                try:

                    recomputed_state = self._apply_transactions(previous_state, current.transactions, i)

                except (RegistryError, GovernanceError):

                    return False

                # Detect cache corruption: cached state must match recomputed state

                if i in self.registry_states and self.registry_states[i] != recomputed_state:

                    return False

                self.registry_states[i] = recomputed_state



        return True



    def chain_work(self) -> int:

        """Total chain work as an integer sum of per-block work."""

        total = 0

        for block in self.chain:

            if isinstance(block, BlockV2):

                total += work_for_target_v2(block.header.target)

            else:

                total += int(work_for_target(block.header.target))

        return total



    def to_dict(self) -> dict[str, Any]:

        return {

            "network_id": self.network_id,

            "chain": [b.to_dict() for b in self.chain],

            "chain_work": self.chain_work(),

            "governance_keys": list(self.governance_keys),

            "governance_threshold": self.governance_threshold,

            "network_identity": self.network_identity.to_dict(),

        }



    @classmethod

    def from_dict(cls, data: dict[str, Any],

                  transaction_validator: Callable[[dict[str, Any]], bool] | None = None) -> Ledger:

        chain = [Block.from_dict(b) if "registry_root" not in b["header"] else BlockV2.from_dict(b) for b in data["chain"]]

        governance_keys = data.get("governance_keys")

        governance_threshold = data.get("governance_threshold")

        if governance_keys is not None and (not isinstance(governance_keys, list) or not all(isinstance(k, str) for k in governance_keys)):

            raise LedgerError("governance_keys must be a list of hex strings")

        if governance_threshold is not None and (not isinstance(governance_threshold, int) or isinstance(governance_threshold, bool)):

            raise LedgerError("governance_threshold must be an integer")



        network_identity: NetworkIdentity | None = None

        identity_data = data.get("network_identity")

        if identity_data is not None:

            try:

                network_identity = NetworkIdentity.from_dict(identity_data)

            except (KeyError, ValueError, TypeError) as exc:

                raise LedgerError(f"invalid network_identity in ledger: {exc}") from exc

            if data.get("network_id") != network_identity.network_id:

                raise LedgerError(

                    "ledger network_id does not match stored network_identity"

                )

        return cls(

            chain,

            transaction_validator=transaction_validator,

            governance_keys=governance_keys,

            governance_threshold=governance_threshold,

            network_identity=network_identity,

        )





def block_encode(block: Block | BlockV2) -> bytes:

    """Encode a block for network/storage."""

    if isinstance(block, BlockV2):

        header_bytes = BinaryCodec.encode_header_v2(block.header.to_dict())

    else:

        header_bytes = BinaryCodec.encode_header(block.header.to_dict())

    tx_count = BinaryCodec.encode_varint(len(block.transactions))

    tx_bytes = b"".join(BinaryCodec.encode_transaction(tx) for tx in block.transactions)

    return header_bytes + tx_count + tx_bytes





def block_decode(data: bytes) -> tuple[Block | BlockV2, int]:

    """Decode a block."""

    if len(data) >= 149 and data[0] == BinaryCodec.TYPE_HEADER and int.from_bytes(data[1:5], "little") == 2:

        header, offset = BinaryCodec.decode_header_v2(data)

        tx_count, offset = BinaryCodec.decode_varint(data, offset)

        transactions = []

        for _ in range(tx_count):

            tx, offset = BinaryCodec.decode_transaction(data, offset)

            transactions.append(tx)

        return BlockV2(BlockHeaderV2.from_dict(header), transactions), offset



    header, offset = BinaryCodec.decode_header(data)

    tx_count, offset = BinaryCodec.decode_varint(data, offset)

    transactions = []

    for _ in range(tx_count):

        tx, offset = BinaryCodec.decode_transaction(data, offset)

        transactions.append(tx)

    return Block(BlockHeader.from_dict(header), transactions), offset
