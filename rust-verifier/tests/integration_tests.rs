use chainbreaker_v2_verifier::*;

#[test]
fn header_v2_roundtrip() {
    let header = HeaderV2 {
        version: 2,
        prev_hash: [0u8; HASH_LEN],
        merkle_root: [1u8; HASH_LEN],
        registry_root: [2u8; HASH_LEN],
        timestamp: 1234567890,
        target: [
            0x00u8, 0x0f, 0xff, 0xff, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
        ],
        nonce: 42,
    };
    let encoded = header.encode();
    assert_eq!(encoded.len(), HEADER_V2_LEN);
    let decoded = HeaderV2::decode_strict(&encoded).unwrap();
    assert_eq!(header, decoded);
}

#[test]
fn sha256d_known() {
    let data = b"hello";
    let got = double_sha256(data);
    // We only verify shape here; exact vectors are in vector_tests.
    assert_eq!(got.len(), 32);
}

#[test]
fn merkle_odd_leaf() {
    let leaves = [[0u8; HASH_LEN], [1u8; HASH_LEN], [2u8; HASH_LEN]];
    let root = merkle_root(&leaves);
    let expected = merkle_root(&[leaves[0], leaves[1], leaves[2], leaves[2]]);
    assert_eq!(root, expected);
}

#[test]
fn hash_object_sorts_keys() {
    let v = serde_json::json!({"b": 1, "a": 2});
    let h1 = hash_object_hex(&v);
    let v2 = serde_json::json!({"a": 2, "b": 1});
    let h2 = hash_object_hex(&v2);
    assert_eq!(h1, h2);
}

#[test]
fn target_be_le_consistency() {
    let target = [
        0x00u8, 0x0f, 0xff, 0xff, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0,
    ];
    let mut le = target;
    le.reverse();
    assert_ne!(target, le);
}

#[test]
fn network_identity_derives_registry_root_and_genesis() {
    let identity = chainbreaker_v2_verifier::network_identity::NetworkIdentity {
        network_id: "chainbreaker-8md-test-vectors".to_string(),
        kind: "test".to_string(),
        governance_keys: vec![
            "aa42478fcf92a320d6e46a5bb805f80b0276894a670d8563476279f96a5b812c".to_string(),
            "ac9c0f87404e2b0cd4c6aa65d6cd74a2cc1159a13f8e46d584ef182fb5a0c3b3".to_string(),
            "c75d922d2c75b43c610891d8ada1f96c06ecc4a8199b0c420c5b8aea23f5d588".to_string(),
        ],
        governance_threshold: 2,
        genesis_timestamp: 1704067200,
    };
    let expected_root =
        hex::decode("88d05861fa8524933091ced2b0c5eba0da2f58c7bd41e62bcdf36b8c7bc36a26").unwrap();
    let derived = chainbreaker_v2_verifier::network_identity::registry_root(&identity);
    assert_eq!(&derived[..], expected_root.as_slice());

    let (header, hash) =
        chainbreaker_v2_verifier::network_identity::derive_genesis(&identity).unwrap();
    assert_eq!(
        hex::encode(header.registry_root),
        "88d05861fa8524933091ced2b0c5eba0da2f58c7bd41e62bcdf36b8c7bc36a26"
    );
    assert_eq!(
        hex::encode(hash),
        "0000618a74626b68a028978681ae432f7677f5dcc75e37ec9c05704d6d11b353"
    );
}

#[test]
fn network_identity_from_json_sorts_governance_keys() {
    let value = serde_json::json!({
        "network_id": "sort-test",
        "kind": "test",
        "governance_keys": [
            "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            "0000000000000000000000000000000000000000000000000000000000000000"
        ],
        "governance_threshold": 1,
        "genesis_timestamp": 1704067200
    });
    let identity =
        chainbreaker_v2_verifier::network_identity::NetworkIdentity::from_json(&value).unwrap();
    assert_eq!(
        identity.governance_keys[0],
        "0000000000000000000000000000000000000000000000000000000000000000"
    );
    assert_eq!(
        identity.governance_keys[1],
        "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    );
}

#[test]
fn network_identity_rejects_threshold_overflow() {
    let value = serde_json::json!({
        "network_id": "threshold-test",
        "kind": "test",
        "governance_keys": [
            "0000000000000000000000000000000000000000000000000000000000000000"
        ],
        "governance_threshold": 256,
        "genesis_timestamp": 1704067200
    });
    let result = chainbreaker_v2_verifier::network_identity::NetworkIdentity::from_json(&value);
    assert!(result.is_err());
}
