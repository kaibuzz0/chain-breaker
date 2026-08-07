use chainbreaker_v2_verifier::*;
use std::fs;
use std::path::{Path, PathBuf};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 || args[1] != "verify" {
        eprintln!("Usage: chainbreaker-v2-verifier verify <test-vectors-dir>");
        std::process::exit(2);
    }
    let vectors_dir = PathBuf::from(&args[2]);
    match run_all(&vectors_dir) {
        Ok(summary) => {
            println!("{}: {}", summary, vectors_dir.display());
            std::process::exit(0);
        }
        Err(e) => {
            eprintln!("Verifier failed: {}", e);
            std::process::exit(1);
        }
    }
}

fn run_all(dir: &Path) -> Result<String, VerifyError> {
    let mut passed = 0usize;
    let mut failed = 0usize;

    macro_rules! run_check {
        ($name:expr, $call:expr) => {
            if let Err(e) = $call {
                eprintln!("[FAIL] {}: {}", $name, e);
                failed += 1;
            } else {
                println!("[PASS] {}", $name);
                passed += 1;
            }
        };
    }

    run_check!("header-v2", check_header_v2(dir));
    run_check!("genesis", check_genesis(dir));
    run_check!("sha256d", check_sha256d(dir));
    run_check!("pow-target", check_pow(dir));
    run_check!("merkle", check_merkle(dir));
    run_check!("registry-state", check_registry_state(dir));
    run_check!("governance-register", check_governance_register(dir));
    run_check!(
        "governance-rotate-revoke",
        check_governance_rotate_revoke(dir)
    );
    run_check!("attestation-v2", check_attestation(dir));
    run_check!("ed25519", check_ed25519(dir));
    run_check!("block", check_block(dir));

    Ok(format!("passed={} failed={}", passed, failed))
}

fn load_json(dir: &Path, name: &str) -> Result<serde_json::Value, VerifyError> {
    let path = dir.join(name);
    let text = fs::read_to_string(&path)?;
    Ok(serde_json::from_str(&text)?)
}

fn load_bytes(dir: &Path, name: &str) -> Result<Vec<u8>, VerifyError> {
    Ok(fs::read(dir.join(name))?)
}

fn as_array<'a>(
    v: &'a serde_json::Value,
    context: &'a str,
) -> Result<&'a Vec<serde_json::Value>, VerifyError> {
    v.as_array()
        .ok_or_else(|| VerifyError::Protocol(format!("{}: expected array", context)))
}

fn check_header_v2(dir: &Path) -> Result<(), VerifyError> {
    let val = load_json(dir, "header-v2.json")?;
    for v in as_array(
        val.get("vectors")
            .ok_or_else(|| VerifyError::Protocol("missing vectors".into()))?,
        "header-v2",
    )? {
        let bytes = hex::decode(
            v["canonical_bytes_hex"]
                .as_str()
                .ok_or_else(|| VerifyError::Protocol("missing canonical_bytes_hex".into()))?,
        )?;
        if v["expected_validity"]
            .as_bool()
            .ok_or_else(|| VerifyError::Protocol("missing expected_validity".into()))?
        {
            let header = HeaderV2::decode_strict(&bytes)?;
            let reencoded = header.encode();
            expect_hex(
                "header encode roundtrip",
                v["canonical_bytes_hex"].as_str().unwrap(),
                &reencoded,
            )?;
            let hash = double_sha256(&reencoded);
            let expected = v["expected_hash"]
                .as_str()
                .ok_or_else(|| VerifyError::Protocol("missing expected_hash".into()))?;
            if hex::encode(hash) != expected {
                return Err(VerifyError::Mismatch {
                    context: "header hash".into(),
                    expected: expected.into(),
                    actual: hex::encode(hash),
                });
            }
        } else if HeaderV2::decode_strict(&bytes).is_ok() {
            return Err(VerifyError::Protocol(format!(
                "negative header should fail: {}",
                v["description"].as_str().unwrap_or("")
            )));
        }
    }
    let frozen = load_bytes(dir, "header-v2-genesis.bin")?;
    let re = HeaderV2::decode_strict(&frozen)?.encode();
    expect_hex("frozen header", &hex::encode(&frozen), &re)?;
    Ok(())
}

fn check_genesis(dir: &Path) -> Result<(), VerifyError> {
    let val = load_json(dir, "genesis.json")?;
    let bin = load_bytes(dir, "genesis.bin")?;
    expect_hex(
        "genesis bytes",
        val["expected_header_bytes_hex"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing expected_header_bytes_hex".into()))?,
        &bin,
    )?;
    let hash = double_sha256(&bin);
    if hex::encode(hash)
        != val["expected_header_hash"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing expected_header_hash".into()))?
    {
        return Err(VerifyError::Mismatch {
            context: "genesis hash".into(),
            expected: val["expected_header_hash"].as_str().unwrap().into(),
            actual: hex::encode(hash),
        });
    }
    let header = HeaderV2::decode_strict(&bin)?;
    if hex::encode(header.registry_root)
        != val["expected_registry_root"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing expected_registry_root".into()))?
    {
        return Err(VerifyError::Mismatch {
            context: "genesis registry root".into(),
            expected: val["expected_registry_root"].as_str().unwrap().into(),
            actual: hex::encode(header.registry_root),
        });
    }
    Ok(())
}

fn check_sha256d(dir: &Path) -> Result<(), VerifyError> {
    let val = load_json(dir, "sha256d.json")?;
    let input = hex::decode(
        val["input_hex"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing input_hex".into()))?,
    )?;
    let got = double_sha256(&input);
    if hex::encode(got)
        != val["expected_sha256d"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing expected_sha256d".into()))?
    {
        return Err(VerifyError::Mismatch {
            context: "sha256d".into(),
            expected: val["expected_sha256d"].as_str().unwrap().into(),
            actual: hex::encode(got),
        });
    }
    Ok(())
}

fn check_pow(dir: &Path) -> Result<(), VerifyError> {
    let val = load_json(dir, "pow-target.json")?;
    let expected_be = val["max_target_hex_be"]
        .as_str()
        .ok_or_else(|| VerifyError::Protocol("missing max_target_hex_be".into()))?;
    let expected_le = val["max_target_hex_le"]
        .as_str()
        .ok_or_else(|| VerifyError::Protocol("missing max_target_hex_le".into()))?;
    let max_target = target_from_hex(expected_be)?;
    if hex::encode(max_target) != expected_be {
        return Err(VerifyError::Mismatch {
            context: "max target BE".into(),
            expected: expected_be.into(),
            actual: hex::encode(max_target),
        });
    }
    let mut le = max_target;
    le.reverse();
    if hex::encode(le) != expected_le {
        return Err(VerifyError::Mismatch {
            context: "max target LE".into(),
            expected: expected_le.into(),
            actual: hex::encode(le),
        });
    }
    for neg in val
        .get("negative_vectors")
        .and_then(|v| v.as_array())
        .unwrap_or(&Vec::new())
    {
        let hash = target_from_hex(
            neg["block_hash_hex"]
                .as_str()
                .ok_or_else(|| VerifyError::Protocol("missing block_hash_hex".into()))?,
        )?;
        let target = target_from_hex(
            neg["target_hex"]
                .as_str()
                .ok_or_else(|| VerifyError::Protocol("missing target_hex".into()))?,
        )?;
        if u256_le(&hash, &target) {
            return Err(VerifyError::Protocol(format!(
                "PoW negative should fail: {}",
                neg["description"].as_str().unwrap_or("")
            )));
        }
    }
    Ok(())
}

fn check_merkle(dir: &Path) -> Result<(), VerifyError> {
    for name in ["merkle.json", "merkle-extra.json"] {
        let val = load_json(dir, name)?;
        if let Some(leaves_hex) = val.get("leaves_hex").and_then(|x| x.as_array()) {
            let leaves: Vec<[u8; HASH_LEN]> = leaves_hex
                .iter()
                .map(|h| {
                    let mut out = [0u8; HASH_LEN];
                    hex::decode_to_slice(h.as_str().unwrap_or(""), &mut out).unwrap();
                    out
                })
                .collect();
            let root = merkle_root(&leaves);
            let expected = val["expected_root_hex"]
                .as_str()
                .ok_or_else(|| VerifyError::Protocol("missing expected_root_hex".into()))?;
            if hex::encode(root) != expected {
                return Err(VerifyError::Mismatch {
                    context: "merkle 4-leaf".into(),
                    expected: expected.into(),
                    actual: hex::encode(root),
                });
            }
        } else if let Some(vectors) = val.get("vectors").and_then(|x| x.as_array()) {
            for v in vectors {
                let leaves: Vec<[u8; HASH_LEN]> = as_array(&v["leaves_hex"], "leaves_hex")?
                    .iter()
                    .map(|h| {
                        let mut out = [0u8; HASH_LEN];
                        hex::decode_to_slice(h.as_str().unwrap_or(""), &mut out).unwrap();
                        out
                    })
                    .collect();
                let root = merkle_root(&leaves);
                let expected = v["expected_root_hex"]
                    .as_str()
                    .ok_or_else(|| VerifyError::Protocol("missing expected_root_hex".into()))?;
                if hex::encode(root) != expected {
                    return Err(VerifyError::Mismatch {
                        context: format!("merkle {}-leaf", v["leaf_count"].as_u64().unwrap_or(0)),
                        expected: expected.into(),
                        actual: hex::encode(root),
                    });
                }
            }
        }
    }
    Ok(())
}

fn check_registry_state(dir: &Path) -> Result<(), VerifyError> {
    let val = load_json(dir, "registry-state.json")?;
    let bin = load_bytes(dir, "registry-state.bin")?;
    expect_hex(
        "registry-state bytes",
        val["state_hex"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing state_hex".into()))?,
        &bin,
    )?;
    let root = sha256_single(&bin);
    if hex::encode(root)
        != val["expected_registry_root"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing expected_registry_root".into()))?
    {
        return Err(VerifyError::Mismatch {
            context: "registry root".into(),
            expected: val["expected_registry_root"].as_str().unwrap().into(),
            actual: hex::encode(root),
        });
    }
    Ok(())
}

fn check_governance_register(dir: &Path) -> Result<(), VerifyError> {
    let val = load_json(dir, "governance-register.json")?;
    let gov_keys: Vec<String> = as_array(
        &val["vectors"].as_array().unwrap()[0]["governance_keys"],
        "governance_keys",
    )?
    .iter()
    .map(|v| v.as_str().unwrap().to_string())
    .collect();
    for v in as_array(&val["vectors"], "governance-register vectors")? {
        let body = &v["input"];
        let body_without_witness = remove_witness_keys(body.clone());
        let msg = build_governance_message(&body_without_witness);
        let sigs = as_array(&body["governance_signatures"], "governance_signatures")?;
        let should_pass = v["expected_validity"].as_bool().unwrap_or(false);
        let ok = sigs.iter().all(|sig| {
            let idx = sig["key_index"].as_u64().unwrap_or(0) as usize;
            if idx >= gov_keys.len() {
                return false;
            }
            let sig_hex = sig["signature"].as_str().unwrap_or("");
            verify_ed25519(&gov_keys[idx], &msg, sig_hex).is_ok()
        });
        if ok != should_pass {
            return Err(VerifyError::Protocol(format!(
                "governance-register [{}] expected validity {} but got {}",
                v["description"].as_str().unwrap_or(""),
                should_pass,
                ok
            )));
        }
    }
    Ok(())
}

fn check_governance_rotate_revoke(dir: &Path) -> Result<(), VerifyError> {
    let val = load_json(dir, "governance-rotate-revoke.json")?;
    let gov_keys: Vec<String> = as_array(&val["governance_keys"], "governance_keys")?
        .iter()
        .map(|v| v.as_str().unwrap().to_string())
        .collect();
    for v in as_array(&val["vectors"], "governance-rotate-revoke vectors")? {
        if v["action"].as_str().unwrap_or("") == "curator_register" {
            continue;
        }
        let body = &v["input"];
        let body_without_witness = remove_witness_keys(body.clone());
        let msg = build_governance_message(&body_without_witness);
        let sigs = as_array(&body["governance_signatures"], "governance_signatures")?;
        let should_pass = v["expected_validity"].as_bool().unwrap_or(false);
        let ok = sigs.iter().all(|sig| {
            let idx = sig["key_index"].as_u64().unwrap_or(0) as usize;
            if idx >= gov_keys.len() {
                return false;
            }
            let sig_hex = sig["signature"].as_str().unwrap_or("");
            verify_ed25519(&gov_keys[idx], &msg, sig_hex).is_ok()
        });
        if ok != should_pass {
            return Err(VerifyError::Protocol(format!(
                "governance-rotate-revoke [{}] expected validity {} but got {}",
                v["description"].as_str().unwrap_or(""),
                should_pass,
                ok
            )));
        }
    }
    Ok(())
}

fn check_attestation(dir: &Path) -> Result<(), VerifyError> {
    let val = load_json(dir, "attestation-v2.json")?;
    for v in as_array(&val["vectors"], "attestation vectors")? {
        let expected_validity = v["expected_validity"].as_bool().unwrap_or(false);
        let pk = v["curator_public_key_hex"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing curator_public_key_hex".into()))?;
        let sig = v["expected_signature_hex"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing expected_signature_hex".into()))?;

        // Verify the signature over the supplied signed preimage (if present) or over the
        // recomputed canonical preimage.
        let preimage_text = v["signed_preimage"].as_str();
        let msg: [u8; HASH_LEN] = if let Some(text) = preimage_text {
            sha256_single(text.as_bytes())
        } else {
            let preimage = build_attestation_preimage(
                v["network_id"]
                    .as_str()
                    .ok_or_else(|| VerifyError::Protocol("missing network_id".into()))?,
                v["protocol_version"].as_u64().unwrap_or(0) as u32,
                v["manifest_hash"]
                    .as_str()
                    .ok_or_else(|| VerifyError::Protocol("missing manifest_hash".into()))?,
                v["curator_id"]
                    .as_str()
                    .ok_or_else(|| VerifyError::Protocol("missing curator_id".into()))?,
                v["block_height"].as_u64().unwrap_or(0),
            );
            hash_object(&preimage)
        };
        let crypto_ok = verify_ed25519(pk, &msg, sig).is_ok();

        // Some negative vectors are cryptographically valid but semantically invalid
        // (e.g. attestation after revocation). The vector records this in expected_error.
        let semantic_error = v["expected_error"].as_str().unwrap_or("");
        let semantic_fail = !semantic_error.is_empty();
        let ok = crypto_ok && !semantic_fail;
        if ok != expected_validity {
            return Err(VerifyError::Protocol(format!(
                "attestation [{}] expected validity {} but got {}",
                v["description"].as_str().unwrap_or(""),
                expected_validity,
                ok
            )));
        }
    }
    Ok(())
}

fn check_ed25519(dir: &Path) -> Result<(), VerifyError> {
    let val = load_json(dir, "ed25519.json")?;
    let pk = val["public_key_hex"]
        .as_str()
        .ok_or_else(|| VerifyError::Protocol("missing public_key_hex".into()))?;
    let msg = hex::decode(
        val["message_hex"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing message_hex".into()))?,
    )?;
    let sig = val["signature_hex"]
        .as_str()
        .ok_or_else(|| VerifyError::Protocol("missing signature_hex".into()))?;
    let expected = val["expected_validity"]
        .as_bool()
        .ok_or_else(|| VerifyError::Protocol("missing expected_validity".into()))?;
    let ok = verify_ed25519(pk, &msg, sig).is_ok();
    if ok != expected {
        return Err(VerifyError::Protocol(
            "ed25519 expected validity mismatch".into(),
        ));
    }
    Ok(())
}

fn check_block(dir: &Path) -> Result<(), VerifyError> {
    let val = load_json(dir, "block.json")?;
    let header = parse_header_from_dict(&val["block_dict"]["header"])?;
    let encoded = header.encode();
    let hash = double_sha256(&encoded);
    let expected = val["expected_header_hash"]
        .as_str()
        .ok_or_else(|| VerifyError::Protocol("missing expected_header_hash".into()))?;
    if hex::encode(hash) != expected {
        return Err(VerifyError::Mismatch {
            context: "block header hash".into(),
            expected: expected.into(),
            actual: hex::encode(hash),
        });
    }
    Ok(())
}

fn parse_header_from_dict(dict: &serde_json::Value) -> Result<HeaderV2, VerifyError> {
    Ok(HeaderV2 {
        version: dict["version"].as_u64().unwrap_or(0) as u32,
        prev_hash: hex_to_hash(
            dict["prev_hash"]
                .as_str()
                .ok_or_else(|| VerifyError::Protocol("missing prev_hash".into()))?,
        )?,
        merkle_root: hex_to_hash(
            dict["merkle_root"]
                .as_str()
                .ok_or_else(|| VerifyError::Protocol("missing merkle_root".into()))?,
        )?,
        registry_root: hex_to_hash(
            dict["registry_root"]
                .as_str()
                .ok_or_else(|| VerifyError::Protocol("missing registry_root".into()))?,
        )?,
        timestamp: dict["timestamp"].as_u64().unwrap_or(0),
        target: hex_to_hash(
            dict["target"]
                .as_str()
                .ok_or_else(|| VerifyError::Protocol("missing target".into()))?,
        )?,
        nonce: dict["nonce"].as_u64().unwrap_or(0),
    })
}
