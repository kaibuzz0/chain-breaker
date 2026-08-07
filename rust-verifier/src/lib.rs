use sha2::{Digest, Sha256};

pub const HEADER_V2_LEN: usize = 149;
pub const NETWORK_ID: &str = "chainbreaker-scripture-v2";
pub const PROTOCOL_VERSION: u32 = 2;

/// Double SHA-256 as used for block headers.
pub fn double_sha256(data: &[u8]) -> [u8; 32] {
    let first = Sha256::digest(data);
    let second = Sha256::digest(first);
    second.into()
}

/// Compare two 256-bit big-endian unsigned integers.
/// Returns true iff `a` is less than or equal to `b`.
pub fn u256_le(a: &[u8; 32], b: &[u8; 32]) -> bool {
    a <= b
}

/// Check whether `hash` satisfies the PoW target.
pub fn satisfies_pow(hash: &[u8; 32], target: &[u8; 32]) -> bool {
    u256_le(hash, target)
}

/// Canonical Header v2 fields.
#[derive(Debug, Clone, PartialEq, Eq)]
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
        let arr = |offset: usize| -> [u8; 32] {
            bytes[offset..offset + 32].try_into().expect("slice length is 32")
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

    /// Compute the double SHA-256 hash of the canonical encoding.
    pub fn hash(&self) -> [u8; 32] {
        double_sha256(&self.encode())
    }
}
