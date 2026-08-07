use sha2::{Digest, Sha256};
use std::convert::TryInto;

pub const HEADER_V2_LEN: usize = 149;
pub const NETWORK_ID: &str = "chainbreaker-scripture-v2";
pub const PROTOCOL_VERSION: u32 = 2;

/// Double SHA-256 as used for block headers.
pub fn double_sha256(data: &[u8]) -> [u8; 32] {
    let first = Sha256::digest(data);
    let second = Sha256::digest(&first);
    second.into()
}

/// Interpret a 32-byte big-endian slice as a 256-bit unsigned integer.
pub fn be_bytes_to_u256(bytes: &[u8; 32]) -> [u64; 4] {
    [
        u64::from_be_bytes(bytes[0..8].try_into().unwrap()),
        u64::from_be_bytes(bytes[8..16].try_into().unwrap()),
        u64::from_be_bytes(bytes[16..24].try_into().unwrap()),
        u64::from_be_bytes(bytes[24..32].try_into().unwrap()),
    ]
}

/// Compare two 256-bit integers in big-endian representation.
/// Returns true iff a <= b.
pub fn u256_le(a: &[u8; 32], b: &[u8; 32]) -> bool {
    for i in 0..32 {
        match a[i].cmp(&b[i]) {
            std::cmp::Ordering::Less => return true,
            std::cmp::Ordering::Greater => return false,
            std::cmp::Ordering::Equal => continue,
        }
    }
    true
}

/// Check whether `hash` satisfies the PoW target.
pub fn satisfies_pow(hash: &[u8; 32], target: &[u8; 32]) -> bool {
    u256_le(hash, target)
}

/// Canonical Header v2 fields (decoded, not re-serialized here).
#[derive(Debug, Clone, PartialEq)]
pub struct HeaderV2 {
    pub version: u32,
    pub prev_hash: [u8; 32],
    pub merkle_root: [u8; 32],
    pub registry_root: [u8; 32],
    pub timestamp: u64,
    pub target: [u8; 32],
    pub nonce: u64,
}

impl HeaderV2 {
    /// Decode from the exact 149-byte canonical form.
    pub fn decode(bytes: &[u8]) -> Result<Self, String> {
        if bytes.len() != HEADER_V2_LEN {
            return Err(format!("expected {} bytes, got {}", HEADER_V2_LEN, bytes.len()));
        }
        if bytes[0] != 0x02 {
            return Err(format!("type marker must be 0x02, got 0x{:02x}", bytes[0]));
        }
        let mut arr = |offset: usize| -> [u8; 32] {
            bytes[offset..offset + 32].try_into().unwrap()
        };
        Ok(HeaderV2 {
            version: u32::from_le_bytes(bytes[1..5].try_into().unwrap()),
            prev_hash: arr(5),
            merkle_root: arr(37),
            registry_root: arr(69),
            timestamp: u64::from_le_bytes(bytes[101..109].try_into().unwrap()),
            target: arr(109),
            nonce: u64::from_le_bytes(bytes[141..149].try_into().unwrap()),
        })
    }

    /// Encode to the exact 149-byte canonical form.
    pub fn encode(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(HEADER_V2_LEN);
        out.push(0x02);
        out.extend_from_slice(&self.version.to_le_bytes());
        out.extend_from_slice(&self.prev_hash);
        out.extend_from_slice(&self.merkle_root);
        out.extend_from_slice(&self.registry_root);
        out.extend_from_slice(&self.timestamp.to_le_bytes());
        out.extend_from_slice(&self.target);
        out.extend_from_slice(&self.nonce.to_le_bytes());
        out
    }

    pub fn hash(&self) -> [u8; 32] {
        double_sha256(&self.encode())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_double_sha256_empty() {
        let got = double_sha256(b"");
        let expected = hex::decode("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
            .unwrap();
        // double sha256 of empty is sha256(sha256(empty)); expected is sha256 of empty
        assert_eq!(got.to_vec(), expected);
    }

    #[test]
    fn test_u256_le_reflexive() {
        let a = [0u8; 32];
        assert!(u256_le(&a, &a));
    }
}
