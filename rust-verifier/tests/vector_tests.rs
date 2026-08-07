use chainbreaker_rust_verifier::{double_sha256, HeaderV2, HEADER_V2_LEN};
use std::fs;

#[test]
fn test_genesis_header_matches_python() {
    let bytes = fs::read("../test-vectors/genesis.bin").expect("genesis.bin missing");
    assert_eq!(bytes.len(), HEADER_V2_LEN);
    let header = HeaderV2::decode(&bytes).expect("decode failed");
    let hash = header.hash();
    let expected = fs::read_to_string("../test-vectors/genesis.hash")
        .expect("genesis.hash missing")
        .trim()
        .to_lowercase();
    assert_eq!(hex::encode(hash), expected);
}
