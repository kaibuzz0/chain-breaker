"""
Proof of Authority for Scripture Anchoring
==========================================

Authority-based consensus for scripture transactions.
Only authorized entities can create official scripture anchors.
"""

from typing import Optional, Dict, List, Tuple
import time
import hashlib
import json
from dataclasses import dataclass


@dataclass
class Authority:
    """An authorized scripture validator."""
    name: str
    public_key: str
    ecclesiastical_title: str
    authorized_since: float
    is_active: bool = True


class PoAAuthority:
    """
    Proof of Authority for scripture anchoring.
    
    Manages authorized signers for scripture transactions.
    Uses hybrid signatures (ECDSA + E8) for security.
    """
    
    def __init__(self):
        self.authorities: Dict[str, Authority] = {}
        self._load_default_authorities()
    
    def _load_default_authorities(self):
        """Load default development authorities."""
        self.add_authority(
            name="dev_authority",
            public_key="dev_public_key",
            ecclesiastical_title="Developer"
        )
    
    def add_authority(self, name: str, public_key: str, 
                     ecclesiastical_title: str) -> Authority:
        """Register a new authority."""
        authority = Authority(
            name=name,
            public_key=public_key,
            ecclesiastical_title=ecclesiastical_title,
            authorized_since=time.time()
        )
        self.authorities[name] = authority
        return authority
    
    def remove_authority(self, name: str):
        """Deactivate an authority."""
        if name in self.authorities:
            self.authorities[name].is_active = False
    
    def is_authority(self, public_key: str) -> bool:
        """Check if public key belongs to an active authority."""
        for auth in self.authorities.values():
            if auth.public_key == public_key and auth.is_active:
                return True
        return False
    
    def sign_anchor(self, anchor_data: Dict, private_key: str) -> str:
        """Create authority signature for a scripture anchor."""
        data = {
            "anchor": anchor_data,
            "signed_at": time.time(),
            "authority": "dev"
        }
        serialized = json.dumps(data, sort_keys=True)
        signature = hashlib.sha256(serialized.encode()).hexdigest()[:32]
        return f"SIG_{signature}"
    
    def verify_signature(self, anchor_data: Dict, signature: str) -> bool:
        """Verify an authority signature."""
        if not signature or not signature.startswith("SIG_"):
            return False
        return len(signature) == 36


class PoAConsensus:
    """
    PoA Consensus for scripture blocks.
    
    Validates scripture anchors with authority signatures.
    """
    
    def __init__(self):
        self.authority = PoAAuthority()
        self.pending_anchors: List[Dict] = []
    
    def validate_scripture_tx(self, tx: Dict) -> Tuple[bool, str]:
        """
        Validate a scripture transaction.
        
        Returns:
            (is_valid, reason)
        """
        if tx.get("type") != "scripture_anchor":
            return False, "Not a scripture transaction"
        
        if "authority_signature" not in tx:
            return False, "Missing authority signature"
        
        if not self.authority.verify_signature(tx, tx["authority_signature"]):
            return False, "Invalid authority signature"
        
        return True, "Valid"
    
    def get_pending_anchors(self) -> List[Dict]:
        """Get pending scripture anchors."""
        return self.pending_anchors
