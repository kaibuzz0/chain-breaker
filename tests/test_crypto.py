
import pytest

from chainbreaker.crypto import HashEngine, MerkleTree, generate_keypair, sign, verify


def test_double_sha256():
    h = HashEngine.double_sha256(b"hello")
    assert len(h) == 32
    assert HashEngine.hex(h) == HashEngine.hex(HashEngine.double_sha256(b"hello"))


def test_merkle_consistency():
    leaves = [HashEngine.sha256(f"tx{i}".encode()) for i in range(4)]
    root1 = MerkleTree(leaves).root
    root2 = MerkleTree(leaves).root
    assert root1 == root2


def test_merkle_proof():
    leaves = [HashEngine.sha256(f"tx{i}".encode()) for i in range(4)]
    tree = MerkleTree(leaves)
    proof = tree.get_proof(1)
    assert MerkleTree.verify_proof(tree.root, leaves[1], proof, 1)


def test_ed25519_sign_verify():
    sk, pk = generate_keypair()
    msg = b"canonical message"
    sig = sign(sk, msg)
    assert verify(pk, msg, sig)
    assert not verify(pk, b"different", sig)
