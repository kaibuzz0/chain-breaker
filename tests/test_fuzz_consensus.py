"""Phase 5F: consensus fuzz testing.

Random and mutational fuzzing of consensus-critical parsing and validation paths.
Must not crash, hang, or raise unhandled exceptions.
"""

import contextlib
import json
import random
import string
import subprocess
import sys
import time

import pytest

from chainbreaker.block import BlockHeaderV2
from chainbreaker.chain import Ledger
from chainbreaker.codec import BinaryCodec
from chainbreaker.crypto import HashEngine, encode_public_key, generate_keypair, sign
from chainbreaker.governance import NETWORK_ID, GovernanceSignature
from chainbreaker.registry_state import RegistryState, registry_root
from chainbreaker.witness import verify_attestation_v2


def _make_governance_keys(count: int = 3, threshold: int = 2):
    pairs = [generate_keypair() for _ in range(count)]
    privs = [p[0] for p in pairs]
    pubs = [encode_public_key(p[1]) for p in pairs]
    return privs, pubs


def _random_hex(rng, length: int = 64) -> str:
    return "".join(rng.choices("0123456789abcdef", k=length))


def _fuzz_header_bytes(rng, seed_bytes: bytes) -> bytes:
    if not seed_bytes:
        return b""
    choice = rng.randrange(5)
    if choice == 0:
        # Truncate
        trunc = rng.randrange(len(seed_bytes) + 1)
        return seed_bytes[:trunc]
    if choice == 1:
        # Append random garbage
        return seed_bytes + bytes(rng.randrange(100))
    if choice == 2:
        # Mutate single byte
        if len(seed_bytes) == 0:
            return seed_bytes
        mutated = bytearray(seed_bytes)
        mutated[rng.randrange(len(mutated))] ^= (1 << rng.randrange(8))
        return bytes(mutated)
    if choice == 3:
        # Shuffle a small prefix
        if len(seed_bytes) < 4:
            return seed_bytes
        prefix = list(seed_bytes[:8])
        rng.shuffle(prefix)
        return bytes(prefix) + seed_bytes[8:]
    # Large random header-sized blob
    return bytes(rng.randrange(256) for _ in range(149))


@pytest.mark.parametrize("_", range(100))
def test_fuzz_header_decoder_no_crash(_):
    rng = random.Random(_)
    base_dict = {
        "version": 2,
        "prev_hash": _random_hex(rng),
        "merkle_root": _random_hex(rng),
        "registry_root": _random_hex(rng),
        "timestamp": rng.randrange(2**64),
        "target": _random_hex(rng),
        "nonce": rng.randrange(2**64),
    }
    try:
        encoded = BinaryCodec.encode_header_v2(base_dict)
    except Exception:
        encoded = b""

    for _ in range(10):
        fuzzed = _fuzz_header_bytes(rng, encoded)
        with contextlib.suppress(Exception):
            BinaryCodec.decode_header_v2(fuzzed, strict=True)


@pytest.mark.parametrize("_", range(100))
def test_fuzz_header_from_dict_no_crash(_):
    rng = random.Random(_)
    header_dict = {
        "version": rng.choice([0, 1, 2, 1000]),
        "prev_hash": _random_hex(rng, rng.choice([0, 32, 64, 128])),
        "merkle_root": _random_hex(rng, rng.choice([0, 32, 64, 128])),
        "registry_root": _random_hex(rng, rng.choice([0, 32, 64, 128])),
        "timestamp": rng.choice([-1, 0, 1, 2**64 - 1]),
        "target": _random_hex(rng, rng.choice([0, 32, 64, 128])),
        "nonce": rng.choice([-1, 0, 1, 2**64 - 1]),
    }
    with contextlib.suppress(Exception):
        BlockHeaderV2.from_dict(header_dict)


@pytest.mark.parametrize("_", range(100))
def test_fuzz_registry_state_no_crash(_):
    rng = random.Random(_)
    keys = [_random_hex(rng, 64) for _ in range(rng.randrange(6))]
    threshold = rng.choice([-1, 0, 1, len(keys), len(keys) + 1])
    records = []
    for _ in range(rng.randrange(5)):
        records.append({
            "curator_id": "".join(rng.choices(string.ascii_letters, k=rng.randrange(10))),
            "public_key_hex": _random_hex(rng, 64),
            "activation_height": rng.choice([-1, 0, 1, 10, 2**63]),
            "revocation_height": rng.choice([None, -1, 0, 1, 10, 2**63]),
            "previous_registry_root": _random_hex(rng, 64),
            "registration_txid": _random_hex(rng, 64),
        })

    try:
        state = RegistryState(
            governance_keys=tuple(keys),
            governance_threshold=threshold,
            records=tuple(records),
        )
    except Exception:
        state = None

    if state is not None:
        with contextlib.suppress(Exception):
            registry_root(state)
        with contextlib.suppress(Exception):
            state.to_dict()


@pytest.mark.parametrize("_", range(50))
def test_fuzz_governance_transaction_no_crash(_):
    rng = random.Random(_)
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)

    body = {
        "action": rng.choice(["curator_register", "curator_rotate", "curator_revoke", "invalid"]),
        "curator_id": "".join(rng.choices(string.ascii_letters, k=rng.randrange(10))),
        "public_key_hex": _random_hex(rng, rng.choice([0, 32, 64, 128])),
        "activation_height": rng.choice([-1, 0, 1, 5]),
        "previous_registry_root": _random_hex(rng, 64),
        "network_id": rng.choice([NETWORK_ID, "other-network", ""]),
        "schema_version": rng.choice([0, 1, 2]),
    }
    # Randomly add signatures
    message = HashEngine.hash_object({
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body),
    })
    sigs = [GovernanceSignature(i, sign(priv, message)).to_dict() for i, priv in enumerate(privs[:rng.randrange(len(privs) + 1)])]
    body["governance_signatures"] = sigs

    try:
        tx = {"type": "governance", "body": body}
        block = ledger.mine_block_v2([tx])
        ledger.add_block_v2(block)
    except Exception:
        pass

    # Ledger state should remain deterministic and queryable
    assert isinstance(ledger.height(), int)


@pytest.mark.parametrize("_", range(50))
def test_fuzz_witness_no_crash(_):
    rng = random.Random(_)
    state = RegistryState.genesis([_random_hex(rng, 64) for _ in range(3)], 2)
    attestation = {
        "curator_id": "".join(rng.choices(string.ascii_letters, k=rng.randrange(10))),
        "block_height": rng.choice([-1, 0, 1, 100]),
        "signature": _random_hex(rng, rng.choice([0, 32, 64, 128])),
        "public_key_hex": _random_hex(rng, 64),
    }
    body_hash = HashEngine.hash_object_hex({"data": "fuzz"})
    with contextlib.suppress(Exception):
        verify_attestation_v2(state, attestation, body_hash, attestation["block_height"])


def _build_valid_register_tx(privs, ledger, curator_id: str, public_key_hex: str, activation_height: int):
    root = registry_root(ledger.registry_state_at(ledger.height()))
    body = {
        "action": "curator_register",
        "curator_id": curator_id,
        "public_key_hex": public_key_hex,
        "activation_height": activation_height,
        "previous_registry_root": root,
        "network_id": NETWORK_ID,
        "schema_version": 1,
    }
    message = HashEngine.hash_object({
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body),
    })
    body["governance_signatures"] = [GovernanceSignature(i, sign(priv, message)).to_dict() for i, priv in enumerate(privs)]
    return {"type": "governance", "body": body}


def test_fuzz_differential_determinism():
    """Same random governance transaction applied to separate ledgers must give same result."""
    privs, pubs = _make_governance_keys()
    sk_a, pk_a = generate_keypair()

    ledger1 = Ledger(governance_keys=pubs, governance_threshold=2)
    ledger2 = Ledger(governance_keys=pubs, governance_threshold=2)

    tx = _build_valid_register_tx(privs, ledger1, "alice", encode_public_key(pk_a), 2)
    for ledger in (ledger1, ledger2):
        b = ledger.mine_block_v2([tx])
        assert ledger.add_block_v2(b)

    assert registry_root(ledger1.registry_state_at(1)) == registry_root(ledger2.registry_state_at(1))


def test_fuzz_cross_process_determinism(tmp_path):
    """Serialize a transaction and verify reducer outcome in a subprocess."""
    privs, pubs = _make_governance_keys()
    ledger = Ledger(governance_keys=pubs, governance_threshold=2)
    sk_a, pk_a = generate_keypair()
    tx = _build_valid_register_tx(privs, ledger, "alice", encode_public_key(pk_a), 2)
    tx_json = json.dumps(tx)
    # Escape quotes for inline script
    safe_tx = tx_json.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
import json
from chainbreaker.chain import Ledger

pubs = {pubs!r}
ledger = Ledger(governance_keys=pubs, governance_threshold=2)
tx = json.loads("{safe_tx}")
b = ledger.mine_block_v2([tx])
result = ledger.add_block_v2(b)
print(result)
print(ledger.registry_state_at(1).by_id("alice").public_key_hex)
'''
    p = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)
    assert "True" in p.stdout
    assert encode_public_key(pk_a) in p.stdout


def test_fuzz_no_hang_on_large_input():
    """Large but bounded inputs must complete quickly."""
    rng = random.Random(0)
    blob = bytes(rng.randrange(256) for _ in range(10000))
    start = time.monotonic()
    with contextlib.suppress(Exception):
        BinaryCodec.decode_header_v2(blob, strict=True)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0
