"""Attestation semantics during reorgs."""

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
from chainbreaker.witness import Curator, CuratorSigner, Registry, verify_attestation


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
    iterations: int = 1_000_000,
) -> list[BlockV2]:
    from chainbreaker.crypto import MerkleTree

    blocks: list[BlockV2] = []
    current = prev
    for i in range(count):
        txs = list(transactions) if (i == 0 and transactions) else []
        tx_hashes = [HashEngine.hash_object(tx) for tx in txs]
        merkle_root = MerkleTree(tx_hashes).root or bytes(32)
        merkle_root_hex = HashEngine.hex(merkle_root)
        header = BlockHeaderV2(
            version=2,
            prev_hash=current.hash,
            merkle_root=merkle_root_hex,
            registry_root="0" * 64,
            timestamp=start_time + i * 600,
            target=current.header.target,
            nonce=0,
        )
        b = BlockV2(header=header, transactions=txs)
        if not b.header.mine(max_iterations=iterations):
            raise RuntimeError("mining failed in test")
        blocks.append(b)
        current = b
    return blocks


def _make_register_transaction(
    state: RegistryState,
    curator_id: str,
    public_key_hex: str,
    activation_height: int,
    context: GovernanceContext,
    keys: list,
) -> dict[str, object]:
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
    sigs = [make_governance_signature(keys[idx][0], body_for_signing, idx) for idx in range(context.threshold)]
    body["governance_signatures"] = [s.to_dict() for s in sigs]
    return {"type": "governance", "body": body}


def _compute_registry_roots(
    chain: list[BlockV2],
    genesis_state: RegistryState,
    context: GovernanceContext,
) -> list[BlockV2]:
    state = genesis_state
    new_chain = [chain[0]]
    for height in range(1, len(chain)):
        block = chain[height]
        pre_root = registry_root(state)
        for tx in block.transactions:
            if tx.get("type") != "governance":
                continue
            parsed = CuratorRegisterTx.from_dict(tx["body"])
            txid = HashEngine.hash_object_hex(tx["body"])
            state = apply_registry_transaction(state, parsed, height, txid, context)
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


def test_attestation_validity_is_branch_specific():
    """An attestation valid on its own chain is not canonical after a reorg."""
    genesis = create_genesis_block(network_id="test-net")
    ctx, keys = _governance_context()
    genesis_state = RegistryState.genesis(list(ctx.public_keys_hex), ctx.threshold)

    base = [genesis] + _mine_suffix(genesis, 2, genesis.header.timestamp + 600)

    # Chain A registers Alice and produces an attestation.
    sk_alice, pk_alice = generate_keypair()
    tx_alice = _make_register_transaction(genesis_state, "alice", encode_public_key(pk_alice), 4, ctx, keys)
    a_suffix = _mine_suffix(base[-1], 2, base[-1].header.timestamp + 600, transactions=[tx_alice])
    chain_a = _compute_registry_roots(base + a_suffix, genesis_state, ctx)

    # Build registry from chain_a state and sign an attestation.
    state_a = genesis_state
    for height in range(1, len(chain_a)):
        for tx in chain_a[height].transactions:
            if tx.get("type") == "governance":
                parsed = CuratorRegisterTx.from_dict(tx["body"])
                state_a = apply_registry_transaction(state_a, parsed, height, HashEngine.hash_object_hex(tx["body"]), ctx)
    registry_a = Registry(entries=[
        Curator(curator_id=r.curator_id, public_key_hex=r.public_key_hex, activation_height=r.activation_height)
        for r in state_a.records
    ])
    signer = CuratorSigner("alice", sk_alice, pk_alice)
    attestation = signer.sign_attestation(network_id="chainbreaker-scripture-v2", version=1, body_hash="cb7c18d4a5...")
    assert verify_attestation(registry_a, attestation, body_hash="cb7c18d4a5...", block_height=len(chain_a) - 1)

    # Chain B wins with more work but does not register Alice.
    sk_bob, pk_bob = generate_keypair()
    tx_bob = _make_register_transaction(genesis_state, "bob", encode_public_key(pk_bob), 4, ctx, keys)
    b_suffix = _mine_suffix(base[-1], 3, base[-1].header.timestamp + 1200, transactions=[tx_bob])
    chain_b = _compute_registry_roots(base + b_suffix, genesis_state, ctx)

    engine = ReorgEngine(chain_a, governance_keys=list(ctx.public_keys_hex), governance_threshold=ctx.threshold)
    result = engine.evaluate_candidate(chain_b)
    assert result.switched is True

    # After switch, canonical registry has Bob, not Alice. The attestation's
    # cryptographic signature remains valid, but it is not canonical-chain history.
    state_b = genesis_state
    for height in range(1, len(chain_b)):
        for tx in chain_b[height].transactions:
            if tx.get("type") == "governance":
                parsed = CuratorRegisterTx.from_dict(tx["body"])
                state_b = apply_registry_transaction(state_b, parsed, height, HashEngine.hash_object_hex(tx["body"]), ctx)
    registry_b = Registry(entries=[
        Curator(curator_id=r.curator_id, public_key_hex=r.public_key_hex, activation_height=r.activation_height)
        for r in state_b.records
    ])
    assert registry_b.get("alice") is None
    assert registry_b.get("bob") is not None

    # Attestation signature still verifies cryptographically against Alice's key,
    # but Alice is not in the canonical registry.
    assert verify_attestation(registry_a, attestation, body_hash="cb7c18d4a5...", block_height=len(chain_a) - 1)
    assert not verify_attestation(registry_b, attestation, body_hash="cb7c18d4a5...", block_height=len(chain_b) - 1)


def test_winning_branch_attestation_still_validates():
    """An attestation on the winning branch remains valid after the switch."""
    genesis = create_genesis_block(network_id="test-net")
    ctx, keys = _governance_context()
    genesis_state = RegistryState.genesis(list(ctx.public_keys_hex), ctx.threshold)

    base = [genesis] + _mine_suffix(genesis, 2, genesis.header.timestamp + 600)

    sk_alice, pk_alice = generate_keypair()
    tx_alice = _make_register_transaction(genesis_state, "alice", encode_public_key(pk_alice), 4, ctx, keys)
    a_suffix = _mine_suffix(base[-1], 1, base[-1].header.timestamp + 600, transactions=[tx_alice])
    _ = _compute_registry_roots(base + a_suffix, genesis_state, ctx)

    sk_bob, pk_bob = generate_keypair()
    tx_bob = _make_register_transaction(genesis_state, "bob", encode_public_key(pk_bob), 4, ctx, keys)
    b_suffix = _mine_suffix(base[-1], 2, base[-1].header.timestamp + 1200, transactions=[tx_bob])
    chain_b = _compute_registry_roots(base + b_suffix, genesis_state, ctx)

    state_b = genesis_state
    for height in range(1, len(chain_b)):
        for tx in chain_b[height].transactions:
            if tx.get("type") == "governance":
                parsed = CuratorRegisterTx.from_dict(tx["body"])
                state_b = apply_registry_transaction(state_b, parsed, height, HashEngine.hash_object_hex(tx["body"]), ctx)
    registry_b = Registry(entries=[
        Curator(curator_id=r.curator_id, public_key_hex=r.public_key_hex, activation_height=r.activation_height)
        for r in state_b.records
    ])
    signer_bob = CuratorSigner("bob", sk_bob, pk_bob)
    attestation_bob = signer_bob.sign_attestation(network_id="chainbreaker-scripture-v2", version=1, body_hash="deadbeef")
    assert verify_attestation(registry_b, attestation_bob, body_hash="deadbeef", block_height=len(chain_b) - 1)
