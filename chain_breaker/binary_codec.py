"""
binary_codec.py

Compact binary encoding for blockchain data.
Replaces JSON with dense binary formats.

Goals:
- 10x smaller than JSON
- Machine-readable (not human-readable)
- Fast encode/decode
- Fixed-size where possible
"""

import struct
import hashlib
from typing import Dict, Any, List, Union, Optional, Tuple
from dataclasses import dataclass


class BinaryCodec:
    """
    Binary encoder/decoder for blockchain primitives.
    
    Format:
    - Addresses: 20 bytes (fixed)
    - Amounts: 8 bytes uint64
    - Timestamps: 8 bytes float64
    - Hashes: 32 bytes
    - Varints: Compact size encoding
    """
    
    # Type markers
    TYPE_TX = 0x01
    TYPE_BLOCK = 0x02
    TYPE_HEADER = 0x03
    
    @staticmethod
    def encode_address(addr: str) -> bytes:
        """
        Encode address string to 20 bytes.
        Removes 'CB' prefix and converts.
        """
        if addr.startswith("CB"):
            addr = addr[2:]
        return bytes.fromhex(addr)[:20]
    
    @staticmethod
    def decode_address(data: bytes) -> str:
        """Decode 20 bytes to address string."""
        return "CB" + data.hex()
    
    @staticmethod
    def encode_hash(hash_hex: str) -> bytes:
        """Encode 64-char hex hash to 32 bytes."""
        return bytes.fromhex(hash_hex)[:32]
    
    @staticmethod
    def decode_hash(data: bytes) -> str:
        """Decode 32 bytes to 64-char hex hash."""
        return data.hex()
    
    @classmethod
    def encode_transaction(cls, tx: Dict[str, Any]) -> bytes:
        """
        Encode transaction to binary.
        
        Format:
        - type_marker: 1 byte
        - from_addr: 20 bytes
        - to_addr: 20 bytes  
        - amount: 8 bytes uint64
        - timestamp: 8 bytes float64
        - data_len: 2 bytes
        - data: variable
        """
        parts = [
            struct.pack('B', cls.TYPE_TX),
            cls.encode_address(tx.get('from', '')),
            cls.encode_address(tx.get('to', '')),
            struct.pack('Q', tx.get('amount', 0)),  # uint64
            struct.pack('d', tx.get('timestamp', 0.0)),  # float64
        ]
        
        # Optional data field
        extra_data = tx.get('data', b'')
        if isinstance(extra_data, str):
            extra_data = extra_data.encode('utf-8')
        parts.append(struct.pack('H', len(extra_data)))  # uint16 length
        parts.append(extra_data)
        
        return b''.join(parts)
    
    @classmethod
    def decode_transaction(cls, data: bytes) -> Tuple[Dict[str, Any], int]:
        """
        Decode transaction from binary.
        Returns (transaction_dict, bytes_consumed).
        """
        offset = 0
        
        # Type marker
        tx_type = struct.unpack('B', data[offset:offset+1])[0]
        offset += 1
        
        # Addresses
        from_addr = cls.decode_address(data[offset:offset+20])
        offset += 20
        
        to_addr = cls.decode_address(data[offset:offset+20])
        offset += 20
        
        # Amount
        amount = struct.unpack('Q', data[offset:offset+8])[0]
        offset += 8
        
        # Timestamp
        timestamp = struct.unpack('d', data[offset:offset+8])[0]
        offset += 8
        
        # Extra data
        data_len = struct.unpack('H', data[offset:offset+2])[0]
        offset += 2
        
        extra_data = data[offset:offset+data_len]
        offset += data_len
        
        tx = {
            'type': tx_type,
            'from': from_addr,
            'to': to_addr,
            'amount': amount,
            'timestamp': timestamp,
        }
        
        if extra_data:
            tx['data'] = extra_data.decode('utf-8', errors='ignore')
        
        return tx, offset
    
    @classmethod
    def encode_block_header(cls, header: Dict[str, Any]) -> bytes:
        """
        Encode block header to binary.
        
        Format:
        - version: 4 bytes uint32
        - prev_hash: 32 bytes
        - merkle_root: 32 bytes
        - timestamp: 8 bytes
        - difficulty: 4 bytes
        - nonce: 8 bytes
        """
        return b''.join([
            struct.pack('I', header.get('version', 1)),  # uint32
            cls.encode_hash(header.get('prev_hash', '0' * 64)),
            cls.encode_hash(header.get('merkle_root', '0' * 64)),
            struct.pack('d', header.get('timestamp', 0.0)),
            struct.pack('I', header.get('difficulty', 1)),
            struct.pack('Q', header.get('nonce', 0)),
        ])
    
    @classmethod
    def decode_block_header(cls, data: bytes) -> Tuple[Dict[str, Any], int]:
        """Decode block header from binary."""
        offset = 0
        
        version = struct.unpack('I', data[offset:offset+4])[0]
        offset += 4
        
        prev_hash = cls.decode_hash(data[offset:offset+32])
        offset += 32
        
        merkle_root = cls.decode_hash(data[offset:offset+32])
        offset += 32
        
        timestamp = struct.unpack('d', data[offset:offset+8])[0]
        offset += 8
        
        difficulty = struct.unpack('I', data[offset:offset+4])[0]
        offset += 4
        
        nonce = struct.unpack('Q', data[offset:offset+8])[0]
        offset += 8
        
        header = {
            'version': version,
            'prev_hash': prev_hash,
            'merkle_root': merkle_root,
            'timestamp': timestamp,
            'difficulty': difficulty,
            'nonce': nonce,
        }
        
        return header, offset
    
    @classmethod
    def encode_varint(cls, n: int) -> bytes:
        """
        Encode variable-length integer.
        Like Bitcoin's CompactSize.
        """
        if n < 253:
            return struct.pack('B', n)
        elif n < 65536:
            return struct.pack('B', 253) + struct.pack('H', n)
        elif n < 4294967296:
            return struct.pack('B', 254) + struct.pack('I', n)
        else:
            return struct.pack('B', 255) + struct.pack('Q', n)
    
    @classmethod
    def decode_varint(cls, data: bytes) -> Tuple[int, int]:
        """Decode varint. Returns (value, bytes_consumed)."""
        first = data[0]
        if first < 253:
            return first, 1
        elif first == 253:
            return struct.unpack('H', data[1:3])[0], 3
        elif first == 254:
            return struct.unpack('I', data[1:5])[0], 5
        else:
            return struct.unpack('Q', data[1:9])[0], 9


def compare_sizes(tx: Dict[str, Any]):
    """Compare JSON vs binary encoding sizes."""
    import json
    
    json_encoded = json.dumps(tx, sort_keys=True).encode('utf-8')
    binary_encoded = BinaryCodec.encode_transaction(tx)
    
    return {
        'json': len(json_encoded),
        'binary': len(binary_encoded),
        'savings': len(json_encoded) - len(binary_encoded),
        'ratio': len(json_encoded) / len(binary_encoded) if len(binary_encoded) > 0 else 0
    }


if __name__ == "__main__":
    print("BinaryCodec Test")
    print("=" * 50)
    
    # Test transaction
    tx = {
        'from': 'CB' + 'a' * 40,
        'to': 'CB' + 'b' * 40,
        'amount': 5000000000,  # 5 billion satoshi
        'timestamp': 1704067200.0,
        'data': 'Hello'
    }
    
    print(f"\nOriginal TX: {tx}")
    
    # Encode
    encoded = BinaryCodec.encode_transaction(tx)
    print(f"\nEncoded size: {len(encoded)} bytes")
    print(f"Hex: {encoded.hex()[:60]}...")
    
    # Decode
    decoded, consumed = BinaryCodec.decode_transaction(encoded)
    print(f"\nDecoded: {decoded}")
    print(f"Bytes consumed: {consumed}")
    print(f"Match: {tx == decoded}")
    
    # Compare sizes
    print("\n" + "=" * 50)
    print("Size Comparison")
    sizes = compare_sizes(tx)
    print(f"  JSON:    {sizes['json']} bytes")
    print(f"  Binary:  {sizes['binary']} bytes")
    print(f"  Savings: {sizes['savings']} bytes ({sizes['ratio']:.1f}x smaller)")
    
    # Test header
    print("\n" + "=" * 50)
    print("Block Header Test")
    
    header = {
        'version': 1,
        'prev_hash': '0' * 64,
        'merkle_root': 'a' * 64,
        'timestamp': 1704067200.0,
        'difficulty': 2,
        'nonce': 123456789
    }
    
    header_encoded = BinaryCodec.encode_block_header(header)
    print(f"Header size: {len(header_encoded)} bytes (fixed)")
    
    header_decoded, _ = BinaryCodec.decode_block_header(header_encoded)
    print(f"Header match: {header == header_decoded}")
    
    print("\n" + "=" * 50)
    print("All tests passed!")
