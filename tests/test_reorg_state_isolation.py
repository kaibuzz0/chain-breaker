"""Registry-state isolation tests for reorgs."""

from __future__ import annotations

from chainbreaker.block import BlockHeaderV2, BlockV2, create_genesis_block
from chainbreaker.crypto import HashEngine, encode_public_key, generate_keypair
from chainbreaker.governance import (
    CuratorRegisterTx,
    GovernanceContext,
    make_governance_signature,
)
from chainbreaker.registry_state import RegistryState, apply_registry_transaction, registry_root
from chainbreaker.reorg import ReorgEngine


def _make_register_transaction(
    state: RegistryState,
    curator_id: str,
    public_key_hex: str,
    activation_height: int,
    context: GovernanceContext,
    keys: list,
) -> dict[str, object]:
    """Build a signed curator_register transaction dict."""
    body = {
        "action": "curator_register",
        "curator_id": curator_id,
        "public_key_hex": public_key_hex,
        "activation_height": activation_height,
        "previous_registry_root": registry_root(state),
        "governance_signatures": [],
        "network_id": "chainbreaker-scripture-v2",
        "schema_version": 1,
    }
    body_for_signing = {k: v for k, v in body.items() if k not in {"governance_signatures", "curator_signature"}}
    sigs = []
    for idx in range(context.threshold):
        sig = make_governance_signature(keys[idx][0], body_for_signing, idx)
        sigs.append(sig)
    body["governance_signatures"] = [s.to_dict() for s in sigs]
    return {"type": "governance", "body": body}


def _governance_context(n: int = 2, threshold: int = 1) -> tuple[GovernanceContext, list[tuple[object, str]]]:
    keys = []
    for _ in range(n):
        sk, pk_obj = generate_keypair()
        pk = encode_public_key(pk_obj)
        keys.append((sk, pk))
    ctx = GovernanceContext(public_keys_hex=[pk for _, pk in keys], threshold=threshold)
    return ctx, keys


def _mine_suffix(
    prev: BlockV2,
    count: int,
    start_time: int,
    transactions: list[dict] | None = None,
    target: int | None = None,
    iterations: int = 1_000_000,
) -> list[BlockV2]:
    """Mine `count` empty v2 blocks with distinct timestamps and optional tx.

    If `transactions` is provided, it is included only in the first mined block.
    """
    blocks: list[BlockV2] = []
    current = prev
    for i in range(count):
        txs = list(transactions) if (i == 0 and transactions) else []
        target_val = target if target is not None else current.header.target
        header = BlockHeaderV2(
            version=2,
            prev_hash=current.hash,
            merkle_root=_merkle(txs),
            registry_root="0" * 64,  # filled later by caller
            timestamp=start_time + i * 600,
            target=target_val,
            nonce=0,
        )
        b = BlockV2(header=header, transactions=txs)
        if not b.header.mine(max_iterations=iterations):
            raise RuntimeError("mining failed in test")
        blocks.append(b)
        current = b
    return blocks


def _merkle(transactions: list[dict]) -> str:
    from chainbreaker.crypto import MerkleTree

    if not transactions:
        return "0" * 64
    tx_hashes = [HashEngine.hash_object(tx) for tx in transactions]
    root = MerkleTree(tx_hashes).root or bytes(32)
    return HashEngine.hex(root)


def _compute_registry_roots(
    chain: list[BlockV2],
    genesis_state: RegistryState,
    context: GovernanceContext,
) -> list[BlockV2]:
    """Recompute registry_root for each block after genesis from transactions.

    A block header commits to the registry state BEFORE its own transactions are
    applied. Because registry_root is part of the header and affects PoW, each
    block is re-mined after its registry_root is updated.
    """
    state = genesis_state
    new_chain = [chain[0]]
    for height in range(1, len(chain)):
        block = chain[height]
        # Header commits to pre-block state
        pre_root = registry_root(state)
        state = _apply_transactions(state, block.transactions, height, context)
        new_header = BlockHeaderV2(
            version=block.header.version,
            prev_hash=new_chain[height - 1].hash,
            merkle_root=block.header.merkle_root,
            registry_root=pre_root,
            timestamp=block.header.timestamp,
            target=block.header.target,
            nonce=0,
        )
        if not new_header.mine(max_iterations=1_000_000):
            raise RuntimeError("re-mining failed in test")
        new_chain.append(BlockV2(header=new_header, transactions=block.transactions))
    return new_chain


def _apply_transactions(state: RegistryState, transactions: list[dict], height: int, context: GovernanceContext) -> RegistryState:
    for tx in transactions:
        if tx.get("type") != "governance":
            continue
        body = tx["body"]
        action = body["action"]
        if action == "curator_register":
            parsed = CuratorRegisterTx.from_dict(body)
            txid = HashEngine.hash_object_hex(body)
            state = apply_registry_transaction(state, parsed, height, txid, context)
    return state


def test_branch_registry_state_isolated():
    """Chain A registers Alice; Chain B registers Bob. Switching branches swaps canonical registry."""
    genesis = create_genesis_block(network_id="test-net")
    ctx, keys = _governance_context()
    genesis_state = RegistryState.genesis(list(ctx.public_keys_hex), ctx.threshold)

    # Base chain
    base_blocks = _mine_suffix(genesis, 2, genesis.header.timestamp + 600)
    base_chain = [genesis] + base_blocks

    # Chain A registers Alice
    sk_alice, pk_alice = generate_keypair()
    tx_alice = _make_register_transaction(
        genesis_state, "alice", encode_public_key(pk_alice), 100, ctx, keys
    )
    a_suffix = _mine_suffix(base_chain[-1], 1, base_chain[-1].header.timestamp + 600, transactions=[tx_alice])
    chain_a = _compute_registry_roots(base_chain + a_suffix, genesis_state, ctx)

    # Chain B registers Bob
    sk_bob, pk_bob = generate_keypair()
    tx_bob = _make_register_transaction(
        genesis_state, "bob", encode_public_key(pk_bob), 100, ctx, keys
    )
    b_suffix = _mine_suffix(base_chain[-1], 2, base_chain[-1].header.timestamp + 1200, transactions=[tx_bob])
    chain_b = _compute_registry_roots(base_chain + b_suffix, genesis_state, ctx)

    engine = ReorgEngine(chain_a, governance_keys=ctx.public_keys_hex, governance_threshold=ctx.threshold)
    result = engine.evaluate_candidate(chain_b)
    assert result.switched is True

    # Verify branch B's canonical state contains bob and not alice
    common_state = genesis_state
    final_state = _apply_branch(common_state, chain_b[result.common_ancestor_height + 1 :], ctx)
    assert final_state.by_id("bob") is not None
    assert final_state.by_id("alice") is None

    # Chain A must remain independently replayable
    state_a = _apply_branch(common_state, chain_a[result.common_ancestor_height + 1 :], ctx)
    assert state_a.by_id("alice") is not None
    assert state_a.by_id("bob") is None


def test_rejected_reorg_leaves_canonical_state_unchanged():
    """A candidate with lower/equal work must not alter registry state."""
    genesis = create_genesis_block(network_id="test-net")
    ctx, keys = _governance_context()
    genesis_state = RegistryState.genesis(list(ctx.public_keys_hex), ctx.threshold)

    base_blocks = _mine_suffix(genesis, 2, genesis.header.timestamp + 600)
    base_chain = [genesis] + base_blocks

    sk_alice, pk_alice = generate_keypair()
    tx_alice = _make_register_transaction(
        genesis_state, "alice", encode_public_key(pk_alice), 100, ctx, keys
    )
    a_suffix = _mine_suffix(base_chain[-1], 2, base_chain[-1].header.timestamp + 600, transactions=[tx_alice])
    chain_a = _compute_registry_roots(base_chain + a_suffix, genesis_state, ctx)

    sk_bob, pk_bob = generate_keypair()
    tx_bob = _make_register_transaction(
        genesis_state, "bob", encode_public_key(pk_bob), 100, ctx, keys
    )
    # Same length as A, so equal work -> no switch
    b_suffix = _mine_suffix(base_chain[-1], 2, base_chain[-1].header.timestamp + 1200, transactions=[tx_bob])
    chain_b = _compute_registry_roots(base_chain + b_suffix, genesis_state, ctx)

    engine = ReorgEngine(chain_a, governance_keys=ctx.public_keys_hex, governance_threshold=ctx.threshold)
    result = engine.evaluate_candidate(chain_b)
    assert result.switched is False

    # Canonical state remains A's state
    final_state = _apply_branch(genesis_state, chain_a[result.common_ancestor_height + 1 :], ctx)
    assert final_state.by_id("alice") is not None
    assert final_state.by_id("bob") is None


def test_same_curator_different_keys_across_branches():
    """The same curator_id with different keys on different branches must not leak."""
    genesis = create_genesis_block(network_id="test-net")
    ctx, keys = _governance_context()
    genesis_state = RegistryState.genesis(list(ctx.public_keys_hex), ctx.threshold)

    base_blocks = _mine_suffix(genesis, 2, genesis.header.timestamp + 600)
    base_chain = [genesis] + base_blocks

    sk_a, pk_a = generate_keypair()
    tx_a = _make_register_transaction(genesis_state, "curator-1", encode_public_key(pk_a), 100, ctx, keys)
    a_suffix = _mine_suffix(base_chain[-1], 2, base_chain[-1].header.timestamp + 600, transactions=[tx_a])
    chain_a = _compute_registry_roots(base_chain + a_suffix, genesis_state, ctx)

    sk_b, pk_b = generate_keypair()
    tx_b = _make_register_transaction(genesis_state, "curator-1", encode_public_key(pk_b), 100, ctx, keys)
    b_suffix = _mine_suffix(base_chain[-1], 3, base_chain[-1].header.timestamp + 1200, transactions=[tx_b])
    chain_b = _compute_registry_roots(base_chain + b_suffix, genesis_state, ctx)

    engine = ReorgEngine(chain_a, governance_keys=ctx.public_keys_hex, governance_threshold=ctx.threshold)
    result = engine.evaluate_candidate(chain_b)
    assert result.switched is True

    final_state = _apply_branch(genesis_state, chain_b[result.common_ancestor_height + 1 :], ctx)
    assert final_state.by_id("curator-1").public_key_hex == encode_public_key(pk_b)

    state_a = _apply_branch(genesis_state, chain_a[result.common_ancestor_height + 1 :], ctx)
    assert state_a.by_id("curator-1").public_key_hex == encode_public_key(pk_a)


def _apply_branch(state: RegistryState, blocks: list[BlockV2], ctx: GovernanceContext) -> RegistryState:
    for height, block in enumerate(blocks, start=1):
        state = _apply_transactions(state, block.transactions, height, ctx)
    return state
