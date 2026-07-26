#!/usr/bin/env python3
"""
Reassemble split bible PDFs
"""

import sys
import json
from pathlib import Path

def reassemble_file(original_name):
    # Load manifest
    with open('split_manifest.json', 'r') as f:
        manifest = json.load(f)
    
    # Find file info
    file_info = None
    for f in manifest['files']:
        if f['original_name'] == original_name:
            file_info = f
            break
    
    if not file_info:
        print(f"❌ File not found in manifest: {original_name}")
        return False
    
    print(f"📦 Reassembling: {original_name}")
    print(f"   Parts: {file_info['num_parts']}")
    
    # Combine parts
    output_path = Path(original_name)
    with open(output_path, 'wb') as outfile:
        for part_name in file_info['parts']:
            part_path = Path(part_name)
            if not part_path.exists():
                print(f"   ❌ Missing part: {part_name}")
                return False
            
            with open(part_path, 'rb') as infile:
                outfile.write(infile.read())
            print(f"   ✓ Added: {part_name}")
    
    print(f"
✅ Reassembled: {output_path}")
    print(f"   Size: {output_path.stat().st_size / (1024*1024):.2f} MB")
    return True

def reassemble_all():
    with open('split_manifest.json', 'r') as f:
        manifest = json.load(f)
    
    for file_info in manifest['files']:
        reassemble_file(file_info['original_name'])
        print()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        reassemble_file(sys.argv[1])
    else:
        reassemble_all()
