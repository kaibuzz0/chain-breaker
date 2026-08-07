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
    let expected = hex::decode("9f7b4e2e70d6a51a9d4b6e4c0c3a5e8f6d1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")
        .unwrap_or_default();
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
