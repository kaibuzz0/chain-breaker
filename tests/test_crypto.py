
import pytest

from chainbreaker.crypto import (
    HashEngine,
    MerkleTree,
    generate_keypair,
    hex_to_target,
    sign,
    target_to_hex,
    verify,
    work_for_target,
)


def test_sha256_vector():
    assert HashEngine.hash_single_hex(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_double_sha256_vector():
    out = HashEngine.hash_double(b"abc")
    assert len(out) == 32
    # Double-SHA256 should not equal single SHA-256
    assert out != HashEngine.hash_single(b"abc")


def test_canonical_json_determinism():
    a = HashEngine.canonical_json({"b": 1, "a": 2})
    b = HashEngine.canonical_json({"a": 2, "b": 1})
    assert a == b


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        HashEngine.canonical_json({"x": float("nan")})


def test_merkle_odd_leaf():
    leaves = [b"a", b"b", b"c"]
    tree = MerkleTree(leaves)
    assert tree.root is not None
    proof = tree.get_proof(2)
    assert MerkleTree.verify_proof(tree.root, leaves[2], proof, 2)


def test_target_roundtrip():
    for t in [1, 2**128, 0xFFFF0000 * 2**208]:
        assert hex_to_target(target_to_hex(t)) == t


def test_work_grows_with_harder_target():
    w1 = work_for_target(0xFFFF000000000000000000000000000000000000000000000000000000000000)
    w2 = work_for_target(0x0000FFFF00000000000000000000000000000000000000000000000000000000)
    assert w2 > w1


def test_ed25519_sign_verify():
    sk, pk = generate_keypair()
    msg = b"hello"
    sig = sign(sk, msg)
    assert verify(pk, msg, sig)
    assert not verify(pk, b"other", sig)


def test_verify_bad_signature_hex():
    sk, pk = generate_keypair()
    assert not verify(pk, b"x", "not-hex")
    assert not verify(pk, b"x", "aa")
