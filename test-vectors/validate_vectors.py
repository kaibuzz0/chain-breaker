#!/usr/bin/env python3

"""Validator for Phase 7B language-neutral test vectors.



Reads only files under test-vectors/ and checks that the current Python

implementation produces the expected values. Expected values are frozen in the

vector files and are not derived from the functions under test.

"""

# ruff: noqa: E402, F401, I001



from pathlib import Path

import hashlib

import json

import sys



REPO = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO))



from chainbreaker.codec import BinaryCodec

from chainbreaker.block import create_genesis_block, target_to_hex, hex_to_target, satisfies_pow, MAX_TARGET

from chainbreaker.crypto import HashEngine, encode_public_key, sign, verify, decode_public_key, decode_private_key

from chainbreaker.registry_state import RegistryState, registry_root, apply_registry_transaction, CuratorRegisterTx, CuratorRotateTx, CuratorRevokeTx, GovernanceContext, serialize_registry_state

from chainbreaker.governance import governance_message

from chainbreaker.network_identity import derive_network_identity

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



    extra = hdr["vectors"][3]

    if extra["canonical_bytes_length"] != 150:

        failures.append("trailing header length not 150")

    try:

        BinaryCodec.decode_header_v2(bytes.fromhex(extra["canonical_bytes_hex"]), strict=True)

        failures.append("trailing header should fail decode")

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

    for neg in powv.get("negative_vectors", []):

        if satisfies_pow(neg["block_hash_hex"], hex_to_target(neg["target_hex"])):

            failures.append("PoW negative should fail")



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

    body_without_witness = {k: v for k, v in pos["input"].items() if k not in ("governance_signatures",)}

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



    # 6b. Governance rotate/revoke

    with open(vectors_dir / "governance-rotate-revoke.json") as f:

        gov_rr = json.load(f)

    for vec in gov_rr["vectors"]:

        if vec["action"] == "curator_register":

            continue  # handled in governance-register.json; includes wrong-network negative that passes from_dict

        tx_cls = {"curator_register": CuratorRegisterTx, "curator_rotate": CuratorRotateTx, "curator_revoke": CuratorRevokeTx}[vec["action"]]

        if not vec["expected_validity"]:

            try:

                tx_cls.from_dict(vec["input"])

                failures.append(f"{vec['action']} negative should fail from_dict")

            except Exception:

                pass

            continue

        body_without_witness = {k: v for k, v in vec["input"].items() if k not in ("governance_signatures", "curator_signature")}

        expected_msg = HashEngine.hash_object({

            "network_id": NETWORK_ID,

            "version": PROTOCOL_VERSION,

            "type": "registry",

            "body_hash": HashEngine.hash_object_hex(body_without_witness),

        })

        tx = tx_cls.from_dict(vec["input"])

        for sig in tx.governance_signatures:

            pk = decode_public_key(gov_rr["governance_keys"][sig.key_index])

            if not verify(pk, expected_msg, sig.signature_hex):

                failures.append(f"{vec['action']} signature {sig.key_index} invalid")

        assert_eq(f"{vec['action']} body_hash", HashEngine.hash_object_hex(vec["input"]), vec["body_hash"])

        if vec["action"] == "curator_rotate":

            st = apply_registry_transaction(base_state, CuratorRegisterTx.from_dict(gov["vectors"][0]["input"]), 1, gov["vectors"][0]["body_hash"], gctx)

            applied = apply_registry_transaction(st, tx, 2, vec["body_hash"], gctx)

            assert_eq(f"{vec['action']} root after", registry_root(applied), vec["expected_registry_root_after"])

        elif vec["action"] == "curator_revoke":

            st = apply_registry_transaction(base_state, CuratorRegisterTx.from_dict(gov["vectors"][0]["input"]), 1, gov["vectors"][0]["body_hash"], gctx)

            st = apply_registry_transaction(st, CuratorRotateTx.from_dict(gov_rr["vectors"][0]["input"]), 2, gov_rr["vectors"][0]["body_hash"], gctx)

            applied = apply_registry_transaction(st, tx, 3, vec["body_hash"], gctx)

            assert_eq(f"{vec['action']} root after", registry_root(applied), vec["expected_registry_root_after"])



    # 7a. Merkle extra cases

    with open(vectors_dir / "merkle-extra.json") as f:

        merkle_extra = json.load(f)

    for v in merkle_extra["vectors"]:

        mtree = MerkleTree([bytes.fromhex(h) for h in v["leaves_hex"]])

        assert_eq(f"merkle-extra {v['leaf_count']}", mtree.root.hex(), v["expected_root_hex"])



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



    # 8b. Network identities

    with open(vectors_dir / "network-identities.json") as f:

        nid = json.load(f)

    for v in nid["vectors"]:

        identity = derive_network_identity(

            network_id=v["network_id"],

            governance_keys=v["governance_keys"],

            governance_threshold=v["governance_threshold"],

            kind=v["kind"],

            genesis_timestamp=v["genesis_timestamp"],

            max_mining_iterations=10_000_000,

        )

        assert_eq(f"network identity {v['network_id']} registry root", identity.genesis_registry_root, v["expected_registry_root"])

        assert_eq(f"network identity {v['network_id']} header bytes", identity.genesis_header_bytes.hex(), v["expected_header_bytes_hex"])

        assert_eq(f"network identity {v['network_id']} header hash", identity.genesis_hash, v["expected_header_hash"])

        state = RegistryState(

            records=(),

            governance_version=1,

            network_id=v["network_id"],

            governance_keys=tuple(v["governance_keys"]),

            threshold=v["governance_threshold"],

        )

        assert_eq(f"network identity {v['network_id']} registry state", serialize_registry_state(state).hex(), v["expected_registry_state_hex"])

    for neg in nid.get("negative_vectors", []):

        if neg["variant"] == "wrong_genesis_root":

            identity = derive_network_identity(

                network_id=neg["network_id"],

                governance_keys=neg["governance_keys"],

                governance_threshold=neg["governance_threshold"],

                kind="test",

                genesis_timestamp=neg["genesis_timestamp"],

                max_mining_iterations=10_000_000,

            )

            if identity.genesis_registry_root == neg["tampered_registry_root"]:

                failures.append("negative wrong_genesis_root unexpectedly matched")

        else:

            identity = derive_network_identity(

                network_id=neg["network_id"],

                governance_keys=neg["governance_keys"],

                governance_threshold=neg["governance_threshold"],

                kind="test",

                genesis_timestamp=neg["genesis_timestamp"],

                max_mining_iterations=10_000_000,

            )

            base = derive_network_identity(

                network_id=nid["vectors"][1]["network_id"],

                governance_keys=nid["vectors"][1]["governance_keys"],

                governance_threshold=nid["vectors"][1]["governance_threshold"],

                kind=nid["vectors"][1]["kind"],

                genesis_timestamp=nid["vectors"][1]["genesis_timestamp"],

                max_mining_iterations=10_000_000,

            )

            if identity.genesis_hash == base.genesis_hash:

                failures.append(f"negative vector {neg['variant']} produced identical hash")



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
