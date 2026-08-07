use chainbreaker_rust_verifier::{double_sha256, HeaderV2, HEADER_V2_LEN};
use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        usage();
    }
    match args[1].as_str() {
        "header-hash" => header_hash(&args),
        "verify" => verify_vectors(&args),
        _ => usage(),
    }
}

fn usage() -> ! {
    eprintln!("Usage: chainbreaker-rust-verifier <header-hash <path> | verify <vectors-dir>>");
    std::process::exit(1);
}

fn header_hash(args: &[String]) {
    if args.len() != 3 {
        usage();
    }
    let path = PathBuf::from(&args[2]);
    let bytes = fs::read(&path).expect("failed to read header file");
    if bytes.len() != HEADER_V2_LEN {
        eprintln!(
            "header must be exactly {} bytes, got {}",
            HEADER_V2_LEN,
            bytes.len()
        );
        std::process::exit(1);
    }
    let header = HeaderV2::decode(&bytes).expect("invalid header");
    println!("{}", hex::encode(header.hash()));
}

fn verify_vectors(args: &[String]) {
    if args.len() != 3 {
        usage();
    }
    let dir = PathBuf::from(&args[2]);
    let genesis = fs::read(dir.join("genesis.bin")).expect("genesis.bin missing");
    assert_eq!(genesis.len(), HEADER_V2_LEN, "genesis header length mismatch");
    let header = HeaderV2::decode(&genesis).expect("genesis header decode failed");
    let expected = fs::read_to_string(dir.join("genesis.hash"))
        .expect("genesis.hash missing")
        .trim()
        .to_ascii_lowercase();
    let got = hex::encode(header.hash());
    if got != expected {
        eprintln!("genesis hash mismatch: got {} expected {}", got, expected);
        std::process::exit(1);
    }
    println!("Rust verifier matched {} frozen vectors", dir.display());
}
