"""Chain-Breaker: a scripture-preservation ledger."""

__version__ = "0.2.0"

from .archive import load_manifest, make_manifest, store_manifest, verify_manifest
from .block import Block, create_genesis_block, header_hash, satisfies_pow
from .chain import Ledger
from .codec import (
    BinaryCodec,
    CodecError,
    SchemaError,
    decode_transaction,
    encode_transaction,
    validate_transaction,
)
from .crypto import (
    HashEngine,
    decode_private_key,
    decode_public_key,
    encode_private_key,
    encode_public_key,
    generate_keypair,
)
from .witness import CuratorSigner, Registry, verify_attestation

__all__ = [
    "BinaryCodec",
    "Block",
    "CodecError",
    "CuratorSigner",
    "HashEngine",
    "Ledger",
    "Registry",
    "SchemaError",
    "create_genesis_block",
    "decode_private_key",
    "decode_public_key",
    "decode_transaction",
    "encode_private_key",
    "encode_public_key",
    "encode_transaction",
    "generate_keypair",
    "header_hash",
    "load_manifest",
    "make_manifest",
    "satisfies_pow",
    "store_manifest",
    "validate_transaction",
    "verify_attestation",
    "verify_manifest",
]
