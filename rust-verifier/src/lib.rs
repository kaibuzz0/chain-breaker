use ed25519_dalek::{Signature, VerifyingKey};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::convert::TryInto;
use std::io;
use thiserror::Error;

pub mod network_identity;

pub const HEADER_V2_LEN: usize = 149;
pub const HASH_LEN: usize = 32;

pub const NETWORK_ID: &str = "chainbreaker-scripture-v2";
pub const GENESIS_TARGET_HEX: &str =
    "0000ffff00000000000000000000000000000000000000000000000000000000";
pub const PROTOCOL_VERSION: u32 = 2;
pub const TYPE_HEADER: u8 = 0x02;

#[derive(Debug, Error)]
pub enum VerifyError {
    #[error("IO error: {0}")]
    Io(#[from] io::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("hex decode error: {0}")]
    Hex(#[from] hex::FromHexError),
    #[error("{0}")]
    Protocol(String),
    #[error("length mismatch expected={expected} got={got}")]
    Length { expected: usize, got: usize },
    #[error("mismatch at {context}: expected {expected:?}, got {actual:?}")]
    Mismatch {
        context: String,
        expected: String,
        actual: String,
    },
}

pub use network_identity::{
    derive_genesis, mine_genesis_header, registry_root as derive_registry_root,
    serialize_genesis_registry_state, NetworkIdentity,
};

pub type Result<T, E = VerifyError> = std::result::Result<T, E>;

pub fn double_sha256(data: &[u8]) -> [u8; HASH_LEN] {
    let first = Sha256::digest(data);
    let second = Sha256::digest(first);
    second.into()
}

pub fn sha256_single(data: &[u8]) -> [u8; HASH_LEN] {
    Sha256::digest(data).into()
}

fn copy_hash(data: &[u8], offset: &mut usize) -> Result<[u8; HASH_LEN]> {
    if data.len() < *offset + HASH_LEN {
        return Err(VerifyError::Protocol("truncated hash".into()));
    }
    let mut out = [0u8; HASH_LEN];
    out.copy_from_slice(&data[*offset..*offset + HASH_LEN]);
    *offset += HASH_LEN;
    Ok(out)
}

fn write_hash(out: &mut [u8], offset: &mut usize, hash: &[u8; HASH_LEN]) {
    out[*offset..*offset + HASH_LEN].copy_from_slice(hash);
    *offset += HASH_LEN;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HeaderV2 {
    pub version: u32,
    pub prev_hash: [u8; HASH_LEN],
    pub merkle_root: [u8; HASH_LEN],
    pub registry_root: [u8; HASH_LEN],
    pub timestamp: u64,
    pub target: [u8; HASH_LEN],
    pub nonce: u64,
}

impl HeaderV2 {
    pub fn decode_strict(data: &[u8]) -> Result<Self> {
        if data.len() != HEADER_V2_LEN {
            return Err(VerifyError::Length {
                expected: HEADER_V2_LEN,
                got: data.len(),
            });
        }
        if data[0] != TYPE_HEADER {
            return Err(VerifyError::Protocol(format!(
                "expected header type 0x02, got 0x{:02x}",
                data[0]
            )));
        }
        let mut offset = 1usize;
        let version = u32::from_le_bytes(data[offset..offset + 4].try_into().unwrap());
        offset += 4;
        let prev_hash = copy_hash(data, &mut offset)?;
        let merkle_root = copy_hash(data, &mut offset)?;
        let registry_root = copy_hash(data, &mut offset)?;
        let timestamp = u64::from_le_bytes(data[offset..offset + 8].try_into().unwrap());
        offset += 8;
        let target = copy_hash(data, &mut offset)?;
        let nonce = u64::from_le_bytes(data[offset..offset + 8].try_into().unwrap());
        Ok(HeaderV2 {
            version,
            prev_hash,
            merkle_root,
            registry_root,
            timestamp,
            target,
            nonce,
        })
    }

    pub fn encode(&self) -> [u8; HEADER_V2_LEN] {
        let mut out = [0u8; HEADER_V2_LEN];
        out[0] = TYPE_HEADER;
        out[1..5].copy_from_slice(&self.version.to_le_bytes());
        let mut off = 5;
        write_hash(&mut out, &mut off, &self.prev_hash);
        write_hash(&mut out, &mut off, &self.merkle_root);
        write_hash(&mut out, &mut off, &self.registry_root);
        out[off..off + 8].copy_from_slice(&self.timestamp.to_le_bytes());
        off += 8;
        write_hash(&mut out, &mut off, &self.target);
        out[off..off + 8].copy_from_slice(&self.nonce.to_le_bytes());
        out
    }

    pub fn hash(&self) -> [u8; HASH_LEN] {
        double_sha256(&self.encode())
    }
}

pub fn target_from_hex(hex: &str) -> Result<[u8; HASH_LEN]> {
    if hex.len() != 64 {
        return Err(VerifyError::Protocol(format!(
            "target hex length {} not 64",
            hex.len()
        )));
    }
    let mut out = [0u8; HASH_LEN];
    hex::decode_to_slice(hex, &mut out)?;
    Ok(out)
}

pub fn merkle_root(leaves: &[[u8; HASH_LEN]]) -> [u8; HASH_LEN] {
    if leaves.is_empty() {
        return [0u8; HASH_LEN];
    }
    let mut level: Vec<[u8; HASH_LEN]> = leaves.to_vec();
    while level.len() > 1 {
        let mut next = Vec::new();
        let mut i = 0;
        while i < level.len() {
            let left = level[i];
            let right = if i + 1 < level.len() {
                level[i + 1]
            } else {
                left
            };
            let mut combined = [0u8; HASH_LEN * 2];
            combined[..HASH_LEN].copy_from_slice(&left);
            combined[HASH_LEN..].copy_from_slice(&right);
            next.push(double_sha256(&combined));
            i += 2;
        }
        level = next;
    }
    level[0]
}

fn escape_json(s: &str) -> String {
    serde_json::to_string(s).unwrap_or_else(|_| format!("\"{}\"", s))
}

fn canonical_json(value: &Value) -> String {
    match value {
        Value::Object(map) => {
            let mut pairs: Vec<(&String, &Value)> = map.iter().collect();
            pairs.sort_by(|a, b| a.0.cmp(b.0));
            let parts: Vec<String> = pairs
                .iter()
                .map(|(k, v)| format!("{}:{}", escape_json(k), canonical_json(v)))
                .collect();
            format!("{{{}}}", parts.join(","))
        }
        Value::Array(arr) => {
            let parts: Vec<String> = arr.iter().map(canonical_json).collect();
            format!("[{}]", parts.join(","))
        }
        Value::String(s) => escape_json(s),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Null => "null".to_string(),
    }
}

pub fn hash_object(value: &Value) -> [u8; HASH_LEN] {
    sha256_single(canonical_json(value).as_bytes())
}

pub fn hash_object_hex(value: &Value) -> String {
    hex::encode(hash_object(value))
}

pub fn verify_ed25519(public_key_hex: &str, message: &[u8], signature_hex: &str) -> Result<()> {
    let mut pk_bytes = [0u8; 32];
    hex::decode_to_slice(public_key_hex, &mut pk_bytes)?;
    let vk = VerifyingKey::from_bytes(&pk_bytes)
        .map_err(|e| VerifyError::Protocol(format!("invalid public key: {:?}", e)))?;
    let mut sig_bytes = [0u8; 64];
    hex::decode_to_slice(signature_hex, &mut sig_bytes)?;
    let sig = Signature::from_bytes(&sig_bytes);
    vk.verify_strict(message, &sig)
        .map_err(|e| VerifyError::Protocol(format!("Ed25519 verification failed: {:?}", e)))?;
    Ok(())
}

pub fn build_attestation_preimage(
    network_id: &str,
    version: u32,
    body_hash: &str,
    curator_id: &str,
    block_height: u64,
) -> Value {
    let mut map = serde_json::Map::new();
    map.insert(
        "network_id".to_string(),
        Value::String(network_id.to_string()),
    );
    map.insert("version".to_string(), Value::Number(version.into()));
    map.insert("type".to_string(), Value::String("attestation".to_string()));
    map.insert(
        "body_hash".to_string(),
        Value::String(body_hash.to_string()),
    );
    map.insert(
        "curator_id".to_string(),
        Value::String(curator_id.to_string()),
    );
    map.insert(
        "block_height".to_string(),
        Value::Number(block_height.into()),
    );
    Value::Object(map)
}

pub fn build_governance_message(body: &Value, network_id: &str) -> [u8; HASH_LEN] {
    let body_hash = hash_object_hex(body);
    let msg = serde_json::json!({
        "network_id": network_id,
        "version": 2,
        "type": "registry",
        "body_hash": body_hash,
    });
    hash_object(&msg)
}

pub fn expect_hex(context: &str, expected_hex: &str, actual: &[u8]) -> Result<()> {
    let expected = hex::decode(expected_hex)?;
    if expected != actual {
        return Err(VerifyError::Mismatch {
            context: context.into(),
            expected: expected_hex.into(),
            actual: hex::encode(actual),
        });
    }
    Ok(())
}

pub fn hex_to_hash(s: &str) -> Result<[u8; HASH_LEN]> {
    let mut out = [0u8; HASH_LEN];
    hex::decode_to_slice(s, &mut out)?;
    Ok(out)
}

pub fn remove_witness_keys(mut value: Value) -> Value {
    if let Some(map) = value.as_object_mut() {
        map.remove("governance_signatures");
        map.remove("curator_signature");
    }
    value
}
