#!/bin/bash
# Chain-Breaker Installation Script for Termux/Android

set -e

echo "=================================="
echo "⛓️  Chain-Breaker Installer"
echo "=================================="
echo ""

# Update Termux
pkg update -y

# Install Python and dependencies
echo "📦 Installing dependencies..."
pkg install -y python python-numpy
pip install ecdsa

# Clone repository (or use local files)
echo "📥 Setting up Chain-Breaker..."
mkdir -p ~/chain-breaker
cd ~/chain-breaker

# Copy files (if not cloned)
if [ ! -f "chain_core.py" ]; then
    echo "⚠️  Please copy Chain-Breaker files to $(pwd)"
    exit 1
fi

# Create launcher
cat > chain-breaker << 'EOF'
#!/bin/bash
cd ~/chain-breaker
python demo.py "$@"
EOF
chmod +x chain-breaker

# Add to PATH
if ! grep -q "chain-breaker" ~/.bashrc; then
    echo 'export PATH=$PATH:~/chain-breaker' >> ~/.bashrc
fi

echo ""
echo "=================================="
echo "✅ Installation Complete!"
echo "=================================="
echo ""
echo "Usage:"
echo "  chain-breaker --mine              # Mine blocks"
echo "  chain-breaker --port 8333         # Start node"
echo "  python test_all.py                # Run tests"
echo ""
echo "Database stored in: ~/chain-breaker/"
