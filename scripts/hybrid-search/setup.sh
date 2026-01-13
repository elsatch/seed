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

# If SEED_DB_PATH is already set, treat it as an override. Otherwise compute platform default.
if [ -z "${SEED_DB_PATH:-}" ]; then
	UNAME_S="$(uname -s 2>/dev/null || echo "")"
	case "$UNAME_S" in
		Darwin)
			SEED_DB_PATH="$HOME/Library/Application Support/seed-daemon/db/db.sqlite"
			;;
		MINGW*|MSYS*|CYGWIN*|Windows_NT)
			SEED_DB_PATH="${APPDATA:-$HOME/AppData/Roaming}/seed-daemon/db/db.sqlite"
			;;
		*)
			SEED_DB_PATH="$HOME/.config/Seed/daemon/db/db.sqlite"
			;;
	esac
fi

if [ -f "$SEED_DB_PATH" ]; then
	echo "Database found: $SEED_DB_PATH"
else
	echo "Warning: database not found at: $SEED_DB_PATH"
	echo "Tip: set SEED_DB_PATH to override, e.g. SEED_DB_PATH=/path/to/db.sqlite ./setup.sh"
fi

echo "Running schema migration..."
SEED_DB_PATH="$SEED_DB_PATH" python3 -c "
import os
from embed_indexer import EmbeddingIndexer
from seed_decoder import DEFAULT_DB_PATH

db_path = os.environ.get('SEED_DB_PATH') or str(DEFAULT_DB_PATH)
indexer = EmbeddingIndexer(db_path)
indexer.ensure_schema()
"
echo "Schema ready"

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
