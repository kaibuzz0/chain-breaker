#!/usr/bin/env python3
"""Validator for Phase 7B language-neutral test vectors.

Reads only files under test-vectors/ and checks that the current Python
implementation produces the expected values. Expected values are frozen in the
vector files and are not derived from the functions under test.
"""

from pathlib import Path
import hashlib
import json
import sys

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from chainbreaker.codec import BinaryCodec
from chainbreaker.block import create_genesis_block, target_to_hex, satisfies_pow, MAX_TARGET
from chainbreaker.crypto import HashEngine, encode_public_key, sign, verify, decode_public_key, decode_private_key
from chainbreaker.registry_state import RegistryState, registry_root, serialize_registry_state, apply_registry_transaction, CuratorRegisterTx, GovernanceContext
from chainbreaker.crypto import MerkleTree

NETWORK_ID = "chainbreaker-scripture-v2"
PROTOCOL_VERSION = 2


def double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def assert_eq(name, a, b):
    if a != b:
        raise AssertionError(f"{name}: {a!r} != {b!r}")


vectors_dir = Path(__file__).resolve().parent


def run():
    failures = []

    # 1. Header V2
    with open(vectors_dir / "header-v2.json") as f:
        hdr = json.load(f)
    pos = hdr["vectors"][0]
    enc = BinaryCodec.encode_header_v2(pos["input"])
    assert_eq("header-v2 positive bytes", enc.hex(), pos["canonical_bytes_hex"])
    assert_eq("header-v2 positive length", len(enc), 149)
    assert_eq("header-v2 positive hash", double_sha256(enc).hex(), pos["expected_hash"])

    bad_type = hdr["vectors"][1]
    if bytes.fromhex(bad_type["canonical_bytes_hex"])[0] != 0x01:
        failures.append("wrong type marker byte not 0x01")
    try:
        BinaryCodec.decode_header_v2(bytes.fromhex(bad_type["canonical_bytes_hex"]))
        failures.append("header-v2 wrong type marker should fail decode")
    except Exception:
        pass

    trunc = hdr["vectors"][2]
    if len(bytes.fromhex(trunc["canonical_bytes_hex"])) != 148:
        failures.append("truncated header length not 148")
    try:
        BinaryCodec.decode_header_v2(bytes.fromhex(trunc["canonical_bytes_hex"]))
        failures.append("truncated header should fail decode")
    except Exception:
        pass

    # 2. Genesis
    with open(vectors_dir / "genesis.json") as f:
        gen = json.load(f)
    with open(vectors_dir / "genesis.bin", "rb") as f:
        gen_bin = f.read()
    assert_eq("genesis bin", gen_bin.hex(), gen["expected_header_bytes_hex"])
    assert_eq("genesis hash", double_sha256(gen_bin).hex(), gen["expected_header_hash"])
    decoded = BinaryCodec.decode_header_v2(gen_bin)
    if isinstance(decoded, tuple):
        decoded = decoded[0]
    assert_eq("genesis registry root", decoded["registry_root"], gen["expected_registry_root"])
    if not satisfies_pow(double_sha256(gen_bin).hex(), MAX_TARGET):
        failures.append("genesis does not satisfy max target")

    # 3. SHA-256d
    with open(vectors_dir / "sha256d.json") as f:
        sha = json.load(f)
    got = double_sha256(bytes.fromhex(sha["input_hex"])).hex()
    assert_eq("sha256d", got, sha["expected_sha256d"])

    # 4. PoW target
    with open(vectors_dir / "pow-target.json") as f:
        powv = json.load(f)
    assert_eq("max target BE", powv["max_target_integer"].to_bytes(32, "big").hex(), powv["max_target_hex_be"])
    assert_eq("max target LE", powv["max_target_integer"].to_bytes(32, "little").hex(), powv["max_target_hex_le"])
    if not (powv["min_target_integer"] <= powv["max_target_integer"]):
        failures.append("min target > max target")

    # 5. Merkle
    with open(vectors_dir / "merkle.json") as f:
        merkle = json.load(f)
    leaves = [bytes.fromhex(h) for h in merkle["leaves_hex"]]
    mtree = MerkleTree(leaves)
    assert_eq("merkle root", mtree.root.hex(), merkle["expected_root_hex"])

    # 6. Governance register
    with open(vectors_dir / "governance-register.json") as f:
        gov = json.load(f)
    pos = gov["vectors"][0]
    tx = CuratorRegisterTx.from_dict(pos["input"])
    body_without_witness = {k: v for k, v in pos["input"].items() if k != "governance_signatures"}
    expected_msg = HashEngine.hash_object({
        "network_id": NETWORK_ID,
        "version": PROTOCOL_VERSION,
        "type": "registry",
        "body_hash": HashEngine.hash_object_hex(body_without_witness),
    })
    for sig in tx.governance_signatures:
        pk = decode_public_key(pos["governance_keys"][sig.key_index])
        if not verify(pk, expected_msg, sig.signature_hex):
            failures.append(f"governance signature {sig.key_index} invalid")
    assert_eq("governance body_hash", HashEngine.hash_object_hex(pos["input"]), pos["body_hash"])

    base_state = RegistryState.genesis(pos["governance_keys"], 2)
    gctx = GovernanceContext(pos["governance_keys"], 2)
    applied = apply_registry_transaction(base_state, tx, 1, pos["body_hash"], gctx)
    assert_eq("governance register root after", registry_root(applied), pos["expected_registry_root_after"])

    neg = gov["vectors"][1]
    if neg["expected_validity"]:
        failures.append("governance negative should be invalid")
    try:
        bad_tx = CuratorRegisterTx.from_dict(neg["input"])
        apply_registry_transaction(base_state, bad_tx, 1, neg["body_hash"], gctx)
        failures.append("governance negative should fail apply")
    except Exception:
        pass

    # 7. Registry state
    with open(vectors_dir / "registry-state.json") as f:
        reg = json.load(f)
    with open(vectors_dir / "registry-state.bin", "rb") as f:
        state_bin = f.read()
    assert_eq("registry state bytes", state_bin.hex(), reg["state_hex"])
    assert_eq("registry root", hashlib.sha256(state_bin).hexdigest(), reg["expected_registry_root"])

    # 8. Attestation V2
    with open(vectors_dir / "attestation-v2.json") as f:
        att = json.load(f)
    pos = att["vectors"][0]
    if len(pos["expected_signature_hex"]) != 128:
        failures.append("attestation signature length not 64 bytes hex")
    pk = decode_public_key(pos["curator_public_key_hex"])
    preimage = {
        "network_id": NETWORK_ID,
        "version": 2,
        "type": "attestation",
        "body_hash": pos["manifest_hash"],
        "curator_id": pos["curator_id"],
        "block_height": pos["block_height"],
    }
    msg = HashEngine.hash_object(preimage)
    if not verify(pk, msg, pos["expected_signature_hex"]):
        failures.append("attestation positive signature invalid")

    neg = att["vectors"][1]
    if neg["expected_validity"]:
        failures.append("attestation negative should be invalid")
    neg_preimage = dict(preimage)
    neg_preimage["curator_id"] = neg["curator_id"]
    neg_msg = HashEngine.hash_object(neg_preimage)
    if verify(pk, neg_msg, neg["expected_signature_hex"]):
        failures.append("attestation negative with wrong curator_id should fail")

    # 9. Block
    with open(vectors_dir / "block.json") as f:
        blockv = json.load(f)
    assert_eq("block header hash", double_sha256(BinaryCodec.encode_header_v2(blockv["block_dict"]["header"])).hex(), blockv["expected_header_hash"])

    # 10. Ed25519
    with open(vectors_dir / "ed25519.json") as f:
        ed = json.load(f)
    pk = decode_public_key(ed["public_key_hex"])
    sk = decode_private_key(ed["private_key_hex"])
    msg = bytes.fromhex(ed["message_hex"])
    assert_eq("ed25519 verify", verify(pk, msg, ed["signature_hex"]), ed["expected_validity"])
    assert_eq("ed25519 sign consistency", sign(sk, msg), ed["signature_hex"])

    print("Validation failures:", failures or "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
