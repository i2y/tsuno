#!/bin/bash
set -e

echo "Building z..."

# Source cargo environment
source ~/.cargo/env

# Build the Rust extension
echo "Building Rust extension with maturin..."
cd pyhtransport
uv run maturin develop --release
cd ..

# Copy the compiled extension to the root directory
echo "Copying compiled extension to root directory..."
cp -f pyhtransport/target/release/pyhtransport.abi3.so pyhtransport.abi3.so 2>/dev/null || true
cp -f pyhtransport/target/release/libpyhtransport.dylib pyhtransport.abi3.so 2>/dev/null || true

echo "Build complete!"
