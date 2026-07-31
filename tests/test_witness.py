
import pytest

from chainbreaker.witness import (
    Registry, Curator, sign_transaction, verify_transaction_witnesses,
)
from chainbreaker.crypto import generate_keypair, encode_public_key


def test_duplicate_curator_rejected():
    sk, pk = generate_keypair()
    r = Registry([Curator("alice", encode_public_key(pk))])
    with pytest.raises(ValueError):
        r.register(Curator("alice", encode_public_key(pk)))


def test_valid_attestation():
    sk, pk = generate_keypair()
    registry = Registry([Curator("vatican-lib", encode_public_key(pk), {"institution": "Vatican Library"})])
    tx = {"version": 1, "type": "scripture", "body": {"ref": "John 3:16"}, "witnesses": []}
    witness = sign_transaction(sk, "vatican-lib", tx, "chainbreaker-scripture-v1")
    tx["witnesses"].append(witness.to_dict())
    assert verify_transaction_witnesses(tx, registry, "chainbreaker-scripture-v1", required=1)


def test_spoofed_curator_id_fails():
    sk, pk = generate_keypair()
    registry = Registry([Curator("vatican-lib", encode_public_key(pk))])
    tx = {"version": 1, "type": "scripture", "body": {"ref": "John 3:16"}, "witnesses": []}
    witness = sign_transaction(sk, "forged-id", tx, "chainbreaker-scripture-v1")
    tx["witnesses"].append(witness.to_dict())
    assert not verify_transaction_witnesses(tx, registry, "chainbreaker-scripture-v1", required=1)
