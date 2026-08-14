use crate::{sha256_single, HeaderV2, Result, VerifyError, HASH_LEN, double_sha256};

/// Network identity parameters for a Protocol V2 network.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NetworkIdentity {
    pub network_id: String,
    pub kind: String,
    pub governance_keys: Vec<String>,
    pub governance_threshold: u8,
    pub genesis_timestamp: u64,
}

impl NetworkIdentity {
    /// Parse from a JSON object vector entry.
    pub fn from_json(value: &serde_json::Value) -> Result<Self> {
        let network_id = value["network_id"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing network_id".into()))?
            .to_string();
        let kind = value["kind"]
            .as_str()
            .ok_or_else(|| VerifyError::Protocol("missing kind".into()))?
            .to_string();
        let governance_keys: Vec<String> = value["governance_keys"]
            .as_array()
            .ok_or_else(|| VerifyError::Protocol("missing governance_keys".into()))?
            .iter()
            .map(|v| {
                v.as_str()
                    .ok_or_else(|| VerifyError::Protocol("governance key must be string".into()))
                    .map(|s| s.to_string())
            })
            .collect::<Result<Vec<String>>>()?;
        let governance_threshold = value["governance_threshold"]
            .as_u64()
            .ok_or_else(|| VerifyError::Protocol("missing governance_threshold".into()))? as u8;
        let genesis_timestamp = value["genesis_timestamp"]
            .as_u64()
            .ok_or_else(|| VerifyError::Protocol("missing genesis_timestamp".into()))?;
        Ok(Self {
            network_id,
            kind,
            governance_keys,
            governance_threshold,
            genesis_timestamp,
        })
    }

    /// Return true if this is the frozen alpha/legacy identity.
    pub fn is_alpha(&self) -> bool {
        self.kind == "alpha"
    }
}

/// Encode a non-negative integer as a Bitcoin-style varint.
fn encode_varint(n: u64) -> Vec<u8> {
    if n < 0xFD {
        vec![n as u8]
    } else if n <= 0xFFFF {
        let mut v = vec![0xFD];
        v.extend_from_slice(&(n as u16).to_le_bytes());
        v
    } else if n <= 0xFFFFFFFF {
        let mut v = vec![0xFE];
        v.extend_from_slice(&(n as u32).to_le_bytes());
        v
    } else {
        let mut v = vec![0xFF];
        v.extend_from_slice(&n.to_le_bytes());
        v
    }
}

/// Encode a length-prefixed UTF-8 string.
fn encode_str(s: &str) -> Vec<u8> {
    let bytes = s.as_bytes();
    let mut out = encode_varint(bytes.len() as u64);
    out.extend_from_slice(bytes);
    out
}

/// Serialize a genesis registry state exactly as Python does.
///
/// Layout:
///   governance_version  u32 LE
///   network_id           length-prefixed UTF-8
///   governance_keys      varint count + 32 bytes each
///   threshold            u8
///   records              varint count (always 0 for genesis)
pub fn serialize_genesis_registry_state(identity: &NetworkIdentity) -> Vec<u8> {
    let mut parts: Vec<u8> = Vec::new();
    // governance schema version = 1
    parts.extend_from_slice(&1u32.to_le_bytes());
    parts.extend_from_slice(&encode_str(&identity.network_id));
    parts.extend_from_slice(&encode_varint(identity.governance_keys.len() as u64));
    for key_hex in &identity.governance_keys {
        let key_bytes = hex::decode(key_hex).expect("valid hex key");
        assert_eq!(key_bytes.len(), 32, "governance key must be 32 bytes");
        parts.extend_from_slice(&key_bytes);
    }
    parts.push(identity.governance_threshold);
    parts.extend_from_slice(&encode_varint(0u64)); // no curator records
    parts
}

/// Compute the registry root from a genesis identity.
pub fn registry_root(identity: &NetworkIdentity) -> [u8; HASH_LEN] {
    sha256_single(&serialize_genesis_registry_state(identity))
}

/// Convert a 64-char hex target to a 32-byte BE array.
fn hex_target_to_bytes(hex: &str) -> [u8; HASH_LEN] {
    let mut out = [0u8; HASH_LEN];
    hex::decode_to_slice(hex, &mut out).expect("valid target hex");
    out
}

/// Mine the genesis header by searching nonces.
pub fn mine_genesis_header(identity: &NetworkIdentity, max_iterations: u64) -> Result<HeaderV2> {
    let target = hex_target_to_bytes(crate::GENESIS_TARGET_HEX);
    let registry_root = registry_root(identity);
    let mut header = HeaderV2 {
        version: 2,
        prev_hash: [0u8; HASH_LEN],
        merkle_root: [0u8; HASH_LEN],
        registry_root,
        timestamp: identity.genesis_timestamp,
        target,
        nonce: 0,
    };
    for _ in 0..max_iterations {
        if header_satisfies_pow(&header.hash(), &target) {
            return Ok(header);
        }
        header.nonce = header.nonce.wrapping_add(1);
    }
    Err(VerifyError::Protocol(format!(
        "failed to mine genesis header for {} within {} iterations",
        identity.network_id, max_iterations
    )))
}

/// Check whether a 32-byte hash satisfies a 32-byte target (both big-endian).
fn header_satisfies_pow(hash: &[u8; HASH_LEN], target: &[u8; HASH_LEN]) -> bool {
    hash <= target
}

/// Derive the genesis header bytes and hash from the identity.
pub fn derive_genesis(identity: &NetworkIdentity) -> Result<(HeaderV2, [u8; HASH_LEN])> {
    let header = mine_genesis_header(identity, 10_000_000)?;
    let hash = double_sha256(&header.encode());
    Ok((header, hash))
}
