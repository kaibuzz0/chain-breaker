#!/usr/bin/env python3
"""
Chain-Breaker Test Suite
Run all self-tests to verify blockchain is working.
"""

import sys
import subprocess

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
    print(f"\nTesting {name}...")
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
