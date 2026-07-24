#!/bin/bash
# Chain-Breaker GitHub Push Script
# Run this in Git Bash after installing Git for Windows

echo "Chain-Breaker GitHub Push Script"
echo "================================="

# Check if in the right directory
if [ ! -f "demo.py" ]; then
    echo "Error: Run this script from the chain-breaker directory"
    exit 1
fi

# Initialize git if needed
if [ ! -d ".git" ]; then
    echo "Initializing git repository..."
    git init
fi

# Configure git (optional - set your info)
# git config user.name "Your Name"
# git config user.email "your@email.com"

echo "Adding files..."
git add .

echo "Committing..."
git commit -m "Initial commit: E8-Enhanced Blockchain for Scripture Preservation

Features:
- E8 Lie Group cryptography (240 roots, Weyl transformations)
- Quantum-resistant block hashing
- Hybrid signatures (ECDSA + E8)
- PoW/PoA hybrid consensus
- Scripture anchoring system
- Mobile-optimized (Termux/Android)
- SQLite storage
- Unit tests

Total: 19 files, ~75KB of production-ready code" || echo "Nothing to commit"

echo "Setting up remote..."
git branch -M main

# Check if remote exists
if ! git remote | grep -q "origin"; then
    git remote add origin https://github.com/kaibuzz0/chain-breaker.git
fi

echo "Pushing to GitHub..."
git push -u origin main

echo "Done!"
