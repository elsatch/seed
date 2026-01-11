#!/bin/bash
# Setup script for Seed hybrid search
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Seed Hybrid Search Setup ==="
echo

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PYTHON_VERSION"

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip -q

# Install dependencies
echo "Installing dependencies (this may take a while for torch)..."
pip install -r requirements.txt

echo
echo "Dependencies installed."

# Detect database path
echo
echo "Checking database..."
if [ "$(uname)" == "Darwin" ]; then
    DB_PATH="$HOME/Library/Application Support/Seed/daemon/db/db.sqlite"
else
    DB_PATH="$HOME/.config/Seed/daemon/db/db.sqlite"
fi

if [ -f "$DB_PATH" ]; then
    echo "Database found: $DB_PATH"

    # Run schema migration
    echo "Running schema migration..."
    python3 -c "
from embed_indexer import EmbeddingIndexer
from seed_decoder import DEFAULT_DB_PATH
indexer = EmbeddingIndexer(DEFAULT_DB_PATH)
indexer.ensure_schema()
"
    echo "Schema ready"
else
    echo "Warning: Database not found at: $DB_PATH"
    echo "Make sure Seed app has run at least once"
fi

echo
echo "=== Setup Complete ==="
echo
echo "Usage:"
echo "  cd $SCRIPT_DIR"
echo "  source .venv/bin/activate"
echo
echo "  # Index content (first run downloads the model)"
echo "  python embed_indexer.py"
echo
echo "  # Search"
echo "  python hybrid_search.py 'your query'"
echo
echo "Available models:"
echo "  - google/embeddinggemma-300m (default, Gemma-based)"
echo "  - BAAI/bge-m3 (multilingual)"
echo "  - Qwen/Qwen3-Embedding-0.6B"
echo "  - Qwen/Qwen3-Embedding-8B (high quality)"
echo
