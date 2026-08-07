use chainbreaker_rust_verifier::{double_sha256, HeaderV2, HEADER_V2_LEN, PROTOCOL_VERSION};
use std::fs;

#[test]
fn genesis_header_matches_python_vector() {
    let bytes = fs::read("../test-vectors/genesis.bin").expect("genesis.bin missing");
    assert_eq!(bytes.len(), HEADER_V2_LEN);
    let header = HeaderV2::decode(&bytes).expect("decode failed");
    let expected = fs::read_to_string("../test-vectors/genesis.hash")
        .expect("genesis.hash missing")
        .trim()
        .to_ascii_lowercase();
    assert_eq!(hex::encode(header.hash()), expected);
}

#[test]
fn header_v2_roundtrip_preserves_fields() {
    let header = HeaderV2 {
        version: PROTOCOL_VERSION,
        prev_hash: [0u8; 32],
        merkle_root: [1u8; 32],
        registry_root: [2u8; 32],
        timestamp: 1_704_067_200,
        target: [
            0x00, 0x0f, 0xff, 0xff, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
        ],
        nonce: 42_129,
    };
    let encoded = header.encode();
    assert_eq!(encoded.len(), HEADER_V2_LEN);
    let decoded = HeaderV2::decode(&encoded).expect("roundtrip decode failed");
    assert_eq!(header, decoded);
    assert_eq!(double_sha256(&encoded), header.hash());
}
