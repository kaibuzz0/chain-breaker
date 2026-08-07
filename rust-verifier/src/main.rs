use chainbreaker_rust_verifier::{double_sha256, HeaderV2, HEADER_V2_LEN};
use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 || args[1] != "header-hash" {
        eprintln!("Usage: chainbreaker-rust-verifier header-hash <path-to-149-byte-header.bin>");
        std::process::exit(1);
    }
    let path = PathBuf::from(&args[2]);
    let bytes = fs::read(&path).expect("failed to read header file");
    if bytes.len() != HEADER_V2_LEN {
        eprintln!("header must be exactly {} bytes, got {}", HEADER_V2_LEN, bytes.len());
        std::process::exit(1);
    }
    let header = HeaderV2::decode(&bytes).expect("invalid header");
    let hash = header.hash();
    println!("{}", hex::encode(hash));
}
