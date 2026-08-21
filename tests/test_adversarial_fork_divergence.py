"""Phase 5D: fork and chain divergence simulation.

Verify competing valid histories maintain independent deterministic state and that
a node can switch between branches without state leakage.
"""


from chainbreaker.chain import Ledger
from chainbreaker.crypto import HashEngine, encode_public_key, generate_keypair, sign
from chainbreaker.governance import (
    NETWORK_ID,
    GovernanceSignature,
)
from chainbreaker.registry_state import registry_root


def _make_governance_keys(count: int = 3, threshold: int = 2):
    pairs = [generate_keypair() for _ in range(count)]
    privs = [p[0] for p in pairs]
    pubs = [encode_public_key(p[1]) for p in pairs]
    return privs, pubs


def _sign_body(privs, body: dict) -> list[dict]:
    # Sign over the transaction body's actual network_id (alpha or derived test identity).
    message = HashEngine.hash_object({
        "network_id": body.get("network_id", NETWORK_ID),
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body),
    })
    return [GovernanceSignature(i, sign(priv, message)).to_dict() for i, priv in enumerate(privs)]


def _build_register_tx(privs, pubs, ledger, curator_id: str, public_key_hex: str, activation_height: int):
    root = registry_root(ledger.registry_state_at(ledger.height()))
    body = {
        "action": "curator_register",
        "curator_id": curator_id,
        "public_key_hex": public_key_hex,
        "activation_height": activation_height,
        "previous_registry_root": root,
        "network_id": ledger.network_id,
        "schema_version": 1,
    }
    body["governance_signatures"] = _sign_body(privs, body)
    return {"type": "governance", "body": body}


def _fork_after_block1(privs, pubs):
    """Create a common chain with genesis + block1, then return two ledgers to fork."""
    base = Ledger(governance_keys=pubs, governance_threshold=2)
    sk_a, pk_a = generate_keypair()
    tx_a = _build_register_tx(privs, pubs, base, "alice", encode_public_key(pk_a), 2)
    assert base.add_block_v2(base.mine_block_v2([tx_a]))
    return base, sk_a, pk_a


def test_fork_creates_independent_registry_states():
    privs, pubs = _make_governance_keys()
    base, sk_a, pk_a = _fork_after_block1(privs, pubs)

    sk_b, pk_b = generate_keypair()
    sk_c, pk_c = generate_keypair()
    pub_b = encode_public_key(pk_b)
    pub_c = encode_public_key(pk_c)

    # Branch A: register bob
    ledger_a = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    tx_bob = _build_register_tx(privs, pubs, ledger_a, "bob", pub_b, 3)
    assert ledger_a.add_block_v2(ledger_a.mine_block_v2([tx_bob]))

    # Branch B: register carol
    ledger_b = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    tx_carol = _build_register_tx(privs, pubs, ledger_b, "carol", pub_c, 3)
    assert ledger_b.add_block_v2(ledger_b.mine_block_v2([tx_carol]))

    state_a = ledger_a.registry_state_at(2)
    state_b = ledger_b.registry_state_at(2)

    assert state_a.by_id("bob") is not None
    assert state_a.by_id("carol") is None
    assert state_b.by_id("carol") is not None
    assert state_b.by_id("bob") is None

    assert registry_root(state_a) != registry_root(state_b)


def test_branch_replay_selects_correct_history():
    privs, pubs = _make_governance_keys()
    base, sk_a, pk_a = _fork_after_block1(privs, pubs)

    sk_b, pk_b = generate_keypair()
    pub_b = encode_public_key(pk_b)

    ledger_a = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    tx_bob = _build_register_tx(privs, pubs, ledger_a, "bob", pub_b, 3)
    block_a = ledger_a.mine_block_v2([tx_bob])
    assert ledger_a.add_block_v2(block_a)

    # New node receives only branch A blocks
    replay = Ledger(chain=[base.chain[0], base.chain[1], block_a], governance_keys=pubs, governance_threshold=2)
    assert replay.registry_state_at(2).by_id("bob") is not None


def test_common_ancestor_state_matches():
    privs, pubs = _make_governance_keys()
    base, *_ = _fork_after_block1(privs, pubs)

    sk_b, pk_b = generate_keypair()
    sk_c, pk_c = generate_keypair()
    pub_b = encode_public_key(pk_b)
    pub_c = encode_public_key(pk_c)

    ledger_a = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    tx_bob = _build_register_tx(privs, pubs, ledger_a, "bob", pub_b, 3)
    assert ledger_a.add_block_v2(ledger_a.mine_block_v2([tx_bob]))

    ledger_b = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    tx_carol = _build_register_tx(privs, pubs, ledger_b, "carol", pub_c, 3)
    assert ledger_b.add_block_v2(ledger_b.mine_block_v2([tx_carol]))

    assert registry_root(ledger_a.registry_state_at(1)) == registry_root(ledger_b.registry_state_at(1))
    assert registry_root(ledger_a.registry_state_at(2)) != registry_root(ledger_b.registry_state_at(2))


def test_ledger_cache_isolation_between_branches():
    privs, pubs = _make_governance_keys()
    base, *_ = _fork_after_block1(privs, pubs)

    sk_b, pk_b = generate_keypair()
    pub_b = encode_public_key(pk_b)

    ledger_a = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    tx_bob = _build_register_tx(privs, pubs, ledger_a, "bob", pub_b, 3)
    assert ledger_a.add_block_v2(ledger_a.mine_block_v2([tx_bob]))

    ledger_b = Ledger(chain=list(ledger_a.chain), governance_keys=pubs, governance_threshold=2)
    # Corrupt ledger_a cache
    ledger_a.registry_states[2] = ledger_a.registry_states[1]
    # ledger_b cache remains correct and replay remains valid
    assert ledger_b.validate_chain()
    assert ledger_b.registry_state_at(2).by_id("bob") is not None


def test_chain_work_selects_higher_work_branch():
    privs, pubs = _make_governance_keys()
    base, *_ = _fork_after_block1(privs, pubs)

    # Branch A mines one block
    ledger_a = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    block_a = ledger_a.mine_block_v2([])
    assert ledger_a.add_block_v2(block_a)

    # Branch B mines two blocks (more chain work)
    ledger_b = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    block_b1 = ledger_b.mine_block_v2([])
    assert ledger_b.add_block_v2(block_b1)
    block_b2 = ledger_b.mine_block_v2([])
    assert ledger_b.add_block_v2(block_b2)

    assert ledger_b.chain_work() > ledger_a.chain_work()


def test_invalid_registry_root_fork_rejected():
    privs, pubs = _make_governance_keys()
    base, *_ = _fork_after_block1(privs, pubs)

    ledger = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    block = ledger.mine_block_v2([])
    # Tamper with registry_root to a different valid root (genesis root)
    block.header.registry_root = registry_root(ledger.registry_state_at(0))
    assert not ledger.add_block_v2(block)


def test_invalid_governance_transition_fork_rejected():
    privs, pubs = _make_governance_keys()
    base, *_ = _fork_after_block1(privs, pubs)

    ledger = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    sk_x, pk_x = generate_keypair()
    # Try to register with only one governance signature (threshold is 2)
    body = {
        "action": "curator_register",
        "curator_id": "eve",
        "public_key_hex": encode_public_key(pk_x),
        "activation_height": 3,
        "previous_registry_root": registry_root(ledger.registry_state_at(1)),
        "network_id": ledger.network_id,
        "schema_version": 1,
    }
    message = HashEngine.hash_object({
        "network_id": ledger.network_id,
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body),
    })
    body["governance_signatures"] = [GovernanceSignature(0, sign(privs[0], message)).to_dict()]
    block = ledger.mine_block_v2([{"type": "governance", "body": body}])
    assert not ledger.add_block_v2(block)


def test_altered_previous_hash_fork_rejected():
    privs, pubs = _make_governance_keys()
    base, *_ = _fork_after_block1(privs, pubs)

    ledger = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    block = ledger.mine_block_v2([])
    # Tamper with prev_hash to genesis hash
    block.header.prev_hash = ledger.chain[0].hash
    assert not ledger.add_block_v2(block)


def test_reorg_to_competing_branch_reconstructs_state():
    """Simulate a reorg: a node follows branch A, then switches to branch B."""
    privs, pubs = _make_governance_keys()
    base, sk_a, pk_a = _fork_after_block1(privs, pubs)

    sk_b, pk_b = generate_keypair()
    sk_c, pk_c = generate_keypair()
    pub_b = encode_public_key(pk_b)
    pub_c = encode_public_key(pk_c)

    # Build branch A and branch B from common base
    ledger_a = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    tx_bob = _build_register_tx(privs, pubs, ledger_a, "bob", pub_b, 3)
    assert ledger_a.add_block_v2(ledger_a.mine_block_v2([tx_bob]))

    ledger_b = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    tx_carol = _build_register_tx(privs, pubs, ledger_b, "carol", pub_c, 3)
    assert ledger_b.add_block_v2(ledger_b.mine_block_v2([tx_carol]))

    # A node that initially follows branch A
    node = Ledger(chain=list(ledger_a.chain), governance_keys=pubs, governance_threshold=2)
    assert node.registry_state_at(2).by_id("bob") is not None

    # Reorg to branch B by replacing the chain
    node2 = Ledger(chain=list(ledger_b.chain), governance_keys=pubs, governance_threshold=2)
    assert node2.validate_chain()
    assert node2.registry_state_at(2).by_id("carol") is not None
    assert node2.registry_state_at(2).by_id("bob") is None


def test_branch_specific_transaction_not_accepted_on_other_branch():
    """A transaction signed against branch A's registry root must not validate on branch B."""
    privs, pubs = _make_governance_keys()
    base, sk_a, pk_a = _fork_after_block1(privs, pubs)

    sk_b, pk_b = generate_keypair()
    pub_b = encode_public_key(pk_b)

    # Build branch A to create a different previous root
    ledger_a = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    tx_bob = _build_register_tx(privs, pubs, ledger_a, "bob", pub_b, 3)
    assert ledger_a.add_block_v2(ledger_a.mine_block_v2([tx_bob]))

    # Try to mine a block on branch B using the transaction signed against branch A's root
    ledger_b = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    sk_c, pk_c = generate_keypair()
    # tx_bob's previous_registry_root is from ledger_a height 1, not ledger_b height 1
    # but ledger_a height 1 == ledger_b height 1 (common ancestor), so it actually is valid here.
    # To make a branch-specific transaction, we need to diverge first.
    tx_diverge = _build_register_tx(privs, pubs, ledger_b, "diverge", encode_public_key(pk_c), 3)
    assert ledger_b.add_block_v2(ledger_b.mine_block_v2([tx_diverge]))

    # Now tx_bob previous root (base height 1) no longer matches ledger_b height 2 previous root
    block_b2 = ledger_b.mine_block_v2([tx_bob])
    assert not ledger_b.add_block_v2(block_b2)


def test_chain_work_is_deterministic():
    privs, pubs = _make_governance_keys()
    base, *_ = _fork_after_block1(privs, pubs)

    ledger1 = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    ledger2 = Ledger(chain=list(base.chain), governance_keys=pubs, governance_threshold=2)
    for _ in range(3):
        assert ledger1.add_block_v2(ledger1.mine_block_v2([]))
        assert ledger2.add_block_v2(ledger2.mine_block_v2([]))
    assert ledger1.chain_work() == ledger2.chain_work()

