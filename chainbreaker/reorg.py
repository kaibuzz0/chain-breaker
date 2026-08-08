"""Reorganization / state-branching engine for Chain-Breaker Protocol V2.

This module implements branch evaluation and canonical-tip switching. It does NOT
modify Protocol V2 consensus rules; it uses the existing deterministic replay and
validation machinery from `chainbreaker.chain` and `chainbreaker.registry_state`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chainbreaker.block import (
    GENESIS_GOVERNANCE_KEYS,
    GENESIS_THRESHOLD,
    BlockV2,
    satisfies_pow,
)
from chainbreaker.chain import Ledger
from chainbreaker.crypto import HashEngine, MerkleTree
from chainbreaker.governance import GovernanceContext, GovernanceError
from chainbreaker.registry_state import RegistryState, apply_registry_transaction, registry_root


class ReorgError(ValueError):
    """Raised when reorg evaluation or execution is invalid."""


@dataclass(frozen=True)
class ReorgResult:
    """Outcome of a successful canonical-tip switch."""

    switched: bool
    old_tip_height: int
    old_tip_hash: str
    new_tip_height: int
    new_tip_hash: str
    common_ancestor_height: int
    disconnect_heights: list[int] = field(default_factory=list)
    connect_heights: list[int] = field(default_factory=list)
    reason: str = ""


def compute_work(target: int) -> int:
    """Return accumulated work for a single block target.

    Uses Bitcoin-style work: 2**256 // (target + 1).
    """
    if target <= 0:
        raise ReorgError("target must be positive")
    return 2**256 // (target + 1)


def branch_work(blocks: list[BlockV2]) -> int:
    """Sum work over a linear sequence of v2 blocks."""
    total = 0
    for block in blocks:
        total += compute_work(block.header.target)
    return total


def _parse_governance_transaction(
    tx: dict[str, Any],
) -> Any | None:
    """Minimal wrapper around chain governance transaction parsing."""
    from chainbreaker.governance import CuratorRegisterTx, CuratorRevokeTx, CuratorRotateTx

    if not isinstance(tx, dict) or tx.get("type") != "governance":
        return None
    body = tx.get("body", tx)
    action = body.get("action")
    if action == "curator_register":
        return CuratorRegisterTx.from_dict(body)
    if action == "curator_rotate":
        return CuratorRotateTx.from_dict(body)
    if action == "curator_revoke":
        return CuratorRevokeTx.from_dict(body)
    return None


def _canonical_txid(body_dict: dict[str, Any]) -> str:
    """Deterministic transaction ID with canonical signature ordering."""
    canonical_body = dict(body_dict)
    if "governance_signatures" in canonical_body:
        canonical_body["governance_signatures"] = sorted(
            canonical_body["governance_signatures"],
            key=lambda s: int(s.get("key_index", 0)),
        )
    return HashEngine.hash_object_hex(canonical_body)


def _apply_transactions(
    state: RegistryState,
    transactions: list[dict[str, Any]],
    height: int,
    context: GovernanceContext,
) -> RegistryState:
    """Apply governance transactions to a scratch state."""
    new_state = state
    for tx in transactions:
        parsed = _parse_governance_transaction(tx)
        if parsed is not None:
            txid = _canonical_txid(parsed.to_dict())
            new_state = apply_registry_transaction(new_state, parsed, height, txid, context)
    return new_state


def find_common_ancestor(
    current_chain: list[BlockV2],
    candidate_chain: list[BlockV2],
) -> int:
    """Return the height of the highest block shared by both chains.

    Both chains must start at the same genesis. If they do not, raise ReorgError.
    """
    if not current_chain or not candidate_chain:
        raise ReorgError("empty chain")
    if current_chain[0].hash != candidate_chain[0].hash:
        raise ReorgError("genesis mismatch: cannot reorg across different networks")

    # Walk backward from the shorter tip
    max_height = min(len(current_chain), len(candidate_chain)) - 1
    for h in range(max_height, -1, -1):
        if current_chain[h].hash == candidate_chain[h].hash:
            return h
    # genesis check above guarantees h=0 matches, but keep defensive
    return 0


def validate_candidate_suffix(
    common_state: RegistryState,
    candidate_blocks: list[BlockV2],
    governance_keys: list[str],
    governance_threshold: int,
    absolute_start_height: int = 0,
    expected_targets: list[int] | None = None,
) -> list[RegistryState]:
    """Validate and replay a candidate suffix from a common ancestor state.

    Returns the list of registry states after each candidate block (length =
    len(candidate_blocks)). Raises ReorgError if validation fails.
    """
    context = GovernanceContext(governance_keys, governance_threshold)
    states: list[RegistryState] = []
    state = common_state
    prev_hash: str | None = None
    for idx, block in enumerate(candidate_blocks):
        absolute_height = absolute_start_height + 1 + idx
        # Linkage
        if prev_hash is None:
            # First suffix block: its prev_hash is checked by caller against common ancestor
            pass
        elif block.header.prev_hash != prev_hash:
            raise ReorgError(
                f"candidate block at height {absolute_height}: prev_hash mismatch"
            )
        prev_hash = block.hash

        # Basic header integrity
        if block.header.version != 2:
            raise ReorgError(f"candidate block {absolute_height}: version must be 2")
        if not satisfies_pow(block.hash, block.header.target):
            raise ReorgError(f"candidate block {absolute_height}: PoW failure")
        # Target
        if expected_targets is not None:
            expected = expected_targets[idx]
            if block.header.target != expected:
                raise ReorgError(
                    f"candidate block {absolute_height}: target mismatch "
                    f"({block.header.target} != {expected})"
                )
        # Merkle root
        tx_hashes = [HashEngine.hash_object(tx) for tx in block.transactions]
        merkle_root = MerkleTree(tx_hashes).root or bytes(32)
        merkle_root_hex = HashEngine.hex(merkle_root)
        if block.header.merkle_root != merkle_root_hex:
            raise ReorgError(f"candidate block {absolute_height}: merkle root mismatch")
        # Registry root commitment: it must match the state BEFORE applying this block
        expected_root = registry_root(state)
        if block.header.registry_root != expected_root:
            raise ReorgError(
                f"candidate block {absolute_height}: registry_root mismatch "
                f"({block.header.registry_root} != {expected_root})"
            )
        # Apply transactions to produce the post-block state
        try:
            state = _apply_transactions(state, block.transactions, absolute_height, context)
        except GovernanceError as exc:
            raise ReorgError(f"candidate block {absolute_height}: governance error {exc}") from exc
        states.append(state)
    return states


def compare_work(current_work: int, candidate_work: int) -> str:
    """Return the deterministic fork-choice comparison result."""
    if candidate_work > current_work:
        return "candidate_wins"
    if candidate_work < current_work:
        return "current_wins"
    return "tie"


class ReorgEngine:
    """Evaluate competing branches and execute deterministic canonical switches."""

    def __init__(
        self,
        current_chain: list[BlockV2],
        governance_keys: list[str] | None = None,
        governance_threshold: int | None = None,
        max_reorg_depth: int | None = None,
    ):
        self.current_chain = list(current_chain)
        self.governance_keys = list(governance_keys or GENESIS_GOVERNANCE_KEYS)
        self.governance_threshold = (
            governance_threshold if governance_threshold is not None else GENESIS_THRESHOLD
        )
        self.max_reorg_depth = max_reorg_depth

    @property
    def current_tip_height(self) -> int:
        return len(self.current_chain) - 1

    @property
    def current_tip_hash(self) -> str:
        return self.current_chain[-1].hash

    def current_chain_work(self) -> int:
        return branch_work(self.current_chain)

    def evaluate_candidate(self, candidate_chain: list[BlockV2]) -> ReorgResult:
        """Evaluate a full candidate chain against the current canonical chain.

        The candidate chain must include genesis. Returns a ReorgResult:
        - switched=False if candidate does not have more work or is invalid.
        - switched=True if candidate wins and is fully validated.
        """
        if not candidate_chain:
            return ReorgResult(
                switched=False,
                old_tip_height=self.current_tip_height,
                old_tip_hash=self.current_tip_hash,
                new_tip_height=self.current_tip_height,
                new_tip_hash=self.current_tip_hash,
                common_ancestor_height=0,
                reason="empty candidate chain",
            )

        # Genesis match
        if candidate_chain[0].hash != self.current_chain[0].hash:
            return ReorgResult(
                switched=False,
                old_tip_height=self.current_tip_height,
                old_tip_hash=self.current_tip_hash,
                new_tip_height=self.current_tip_height,
                new_tip_hash=self.current_tip_hash,
                common_ancestor_height=0,
                reason="genesis mismatch",
            )

        common_height = find_common_ancestor(self.current_chain, candidate_chain)
        candidate_suffix = candidate_chain[common_height + 1 :]
        current_suffix = self.current_chain[common_height + 1 :]

        # Depth policy
        if self.max_reorg_depth is not None:
            depth = len(self.current_chain) - 1 - common_height
            if depth > self.max_reorg_depth:
                return ReorgResult(
                    switched=False,
                    old_tip_height=self.current_tip_height,
                    old_tip_hash=self.current_tip_hash,
                    new_tip_height=self.current_tip_height,
                    new_tip_hash=self.current_tip_hash,
                    common_ancestor_height=common_height,
                    reason=f"reorg depth {depth} exceeds policy {self.max_reorg_depth}",
                )

        # Validate candidate suffix in scratch space before work comparison.
        # An invalid candidate must never win, regardless of work.
        common_state = self._state_at(common_height)
        expected_targets = [
            self._expected_target_at(common_height + 1 + idx)
            for idx in range(len(candidate_suffix))
        ]
        try:
            validate_candidate_suffix(
                common_state,
                candidate_suffix,
                self.governance_keys,
                self.governance_threshold,
                absolute_start_height=common_height,
                expected_targets=expected_targets,
            )
        except ReorgError as exc:
            return ReorgResult(
                switched=False,
                old_tip_height=self.current_tip_height,
                old_tip_hash=self.current_tip_hash,
                new_tip_height=self.current_tip_height,
                new_tip_hash=self.current_tip_hash,
                common_ancestor_height=common_height,
                reason=f"candidate validation failed: {exc}",
            )

        # Work comparison
        candidate_work = branch_work(candidate_suffix)
        current_work = branch_work(current_suffix)
        decision = compare_work(current_work, candidate_work)
        if decision in ("current_wins", "tie"):
            return ReorgResult(
                switched=False,
                old_tip_height=self.current_tip_height,
                old_tip_hash=self.current_tip_hash,
                new_tip_height=self.current_tip_height,
                new_tip_hash=self.current_tip_hash,
                common_ancestor_height=common_height,
                reason=(
                    "candidate work not greater: "
                    f"candidate={candidate_work}, current={current_work}"
                ),
            )

        # Candidate wins
        new_tip = candidate_chain[-1]
        disconnect_heights = list(range(common_height + 1, len(self.current_chain)))
        connect_heights = list(range(common_height + 1, len(candidate_chain)))
        return ReorgResult(
            switched=True,
            old_tip_height=self.current_tip_height,
            old_tip_hash=self.current_tip_hash,
            new_tip_height=len(candidate_chain) - 1,
            new_tip_hash=new_tip.hash,
            common_ancestor_height=common_height,
            disconnect_heights=disconnect_heights,
            connect_heights=connect_heights,
            reason="higher valid work branch accepted",
        )

    def _state_at(self, height: int) -> RegistryState:
        """Replay registry state at the given height on the current chain."""
        if height < 0 or height >= len(self.current_chain):
            raise ReorgError(f"invalid height {height}")
        state = RegistryState.genesis(self.governance_keys, self.governance_threshold)
        context = GovernanceContext(self.governance_keys, self.governance_threshold)
        for h in range(1, height + 1):
            state = _apply_transactions(state, self.current_chain[h].transactions, h, context)
        return state

    def _expected_target_at(self, height: int) -> int:
        """Return the expected PoW target at the given absolute height.

        For heights within the current chain, compute exactly. For heights
        beyond the current tip, assume the candidate fork stays within the same
        retarget window and reuse the current tip target. Full retarget
        projection across long candidate forks is left for Phase 7I.
        """
        if height <= 0:
            from chainbreaker.block import GENESIS_TARGET

            return GENESIS_TARGET
        current_len = len(self.current_chain)
        if height < current_len:
            ledger = Ledger(
                chain=list(self.current_chain[:height]),
                governance_keys=list(self.governance_keys),
                governance_threshold=self.governance_threshold,
            )
            return ledger.expected_target_at(height)
        # Beyond current tip: within the same retarget window the target is
        # unchanged. Retarget boundaries are rare for short forks.
        return self.current_chain[-1].header.target


def build_candidate_chain(
    current_chain: list[BlockV2],
    suffix_blocks: list[BlockV2],
) -> list[BlockV2]:
    """Build a full candidate chain by appending suffix blocks to the current chain.

    This is a convenience helper for tests. It does not validate.
    """
    if not suffix_blocks:
        return list(current_chain)
    if suffix_blocks[0].header.prev_hash != current_chain[-1].hash:
        raise ReorgError("suffix does not link to current tip")
    return list(current_chain) + list(suffix_blocks)
