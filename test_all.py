
import os
import sys

#!/usr/bin/env python3
"""
Chain-Breaker Test Suite
Run all self-tests to verify blockchain is working.
"""

import sys
# SECURITY: Removed subprocess - use safe alternatives
# import subprocess

tests = [
    ('E8 Core', 'e8_core.py'),
    ('Mesh Node', 'mesh_node.py'),
]

print("=" * 70)
print("🧪 CHAIN-BREAKER TEST SUITE")
print("=" * 70)
print()

all_passed = True
for name, file in tests:
    print(f"\n# SECURITY FIX: Input validation
def validate_input(data, expected_type=None, max_length=None):
    """Validate and sanitize input data"""
    if data is None:
        return None
    if expected_type and not isinstance(data, expected_type):
        raise TypeError(f"Expected {expected_type}, got {type(data)}")
    if max_length and len(str(data)) > max_length:
        raise ValueError(f"Input exceeds maximum length of {max_length}")
    # Sanitize string inputs
    if isinstance(data, str):
        # Remove potentially dangerous characters
        dangerous = [';', '&&', '||', '`', '$', '\x00']
        for char in dangerous:
            data = data.replace(char, '')
    return data

\nTesting {name}...")
    result = subprocess.run([sys.executable, file], 
                          capture_output=True, timeout=30)
    if result.returncode == 0:
        print(f"   ✅ {name} PASSED")
    else:
        print(f"   ❌ {name} FAILED")
        all_passed = False

print()
print("=" * 70)
if all_passed:
    print("🎉 ALL TESTS PASSED - Blockchain is operational!")
else:
    print("⚠️  SOME TESTS FAILED")
print("=" * 70)
