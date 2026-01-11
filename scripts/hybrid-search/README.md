# Seed Hybrid Search

Hybrid semantic + keyword search over locally replicated Seed documents using [sqlite-vec](https://alexgarcia.xyz/sqlite-vec/) for fast vector similarity search.

## Features

- **Hybrid retrieval**: Combines vector embeddings (semantic) with FTS5 (keyword) using Reciprocal Rank Fusion
- **Fast vector search**: Uses sqlite-vec for efficient KNN queries (successor to sqlite-vss)
- **Multiple embedding backends**: Ollama (Gemma, nomic-embed-text) or sentence-transformers
- **Indexes documents & comments**: Extracts text from Change and Comment blobs

## Prerequisites

1. **Seed desktop app** installed and run at least once (to create the database)
2. **Python 3.10+**
3. **Ollama** (recommended) for local embeddings

## Installation

### 1. Clone and setup

```bash
cd seed/scripts/hybrid-search
./setup.sh
```

This will:
- Create a Python virtual environment
- Install dependencies (including sqlite-vec)
- Check for Ollama and database

### 2. Install Ollama and embedding model

```bash
# Install Ollama (if not already installed)
# macOS: brew install ollama
# Linux: curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama
ollama serve

# Pull embedding model (in another terminal)
ollama pull nomic-embed-text
```

## Usage

### Activate environment

```bash
cd seed/scripts/hybrid-search
source .venv/bin/activate
```

### Index content

```bash
# Index all unembedded documents and comments
python embed_indexer.py

# Index with specific model
python embed_indexer.py --model gemma2:2b

# Index only titles
python embed_indexer.py --types title

# Limit number of items
python embed_indexer.py --max 100

# Check statistics
python embed_indexer.py --stats
```

### Search

```bash
# Hybrid search (recommended)
python hybrid_search.py "your search query"

# Semantic-only search
python hybrid_search.py "query" --mode semantic

# Keyword-only search
python hybrid_search.py "query" --mode keyword

# JSON output
python hybrid_search.py "query" --format json

# Search specific content types
python hybrid_search.py "query" --types title document

# Adjust semantic weight (0.7 = more semantic, 0.3 = more keyword)
python hybrid_search.py "query" --weight 0.7
```

## Database Locations

| Platform | Path |
|----------|------|
| Linux | `~/.config/Seed/daemon/db/db.sqlite` |
| macOS | `~/Library/Application Support/Seed/daemon/db/db.sqlite` |
| Windows | `%APPDATA%/Seed/daemon/db/db.sqlite` |

## Embedding Models

| Model | Backend | Dimensions | Notes |
|-------|---------|------------|-------|
| `nomic-embed-text` | Ollama | 768 | Recommended, good balance |
| `gemma2:2b` | Ollama | 2048 | Higher quality, slower |
| `mxbai-embed-large` | Ollama | 1024 | Good alternative |
| `all-minilm` | Ollama | 384 | Fast, lower quality |
| `all-MiniLM-L6-v2` | sentence-transformers | 384 | Fallback option |

## How It Works

1. **Blob Decoding**: Reads Zstd-compressed DAG-CBOR blobs from Seed's SQLite database
2. **Text Extraction**: Extracts text from Change (document) and Comment blobs
3. **Embedding**: Generates vector embeddings using Ollama or sentence-transformers
4. **Vector Index**: Stores embeddings in sqlite-vec virtual table for fast KNN search
5. **Hybrid Search**: Combines vector similarity + FTS5 BM25 using Reciprocal Rank Fusion

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  embed_indexer  │────▶│  Seed SQLite DB  │◀────│  hybrid_search  │
│   (indexing)    │     │                  │     │   (querying)    │
└────────┬────────┘     │  - blobs         │     └────────┬────────┘
         │              │  - fts (FTS5)    │              │
         ▼              │  - embeddings    │              ▼
┌─────────────────┐     │  - vec_embeddings│     ┌─────────────────┐
│  Ollama API     │     │    (sqlite-vec)  │     │  Ollama API     │
│  (embeddings)   │     └──────────────────┘     │  (query embed)  │
└─────────────────┘                              └─────────────────┘
```

## Troubleshooting

### sqlite-vec not loading

On macOS with system Python, you may need Homebrew Python:
```bash
brew install python
/opt/homebrew/bin/python3 -m venv .venv
```

### Ollama connection refused

Make sure Ollama is running:
```bash
ollama serve
```

### Database not found

Ensure Seed desktop app has run at least once to create the database.

### MacOS SQLite extension error

The bundled macOS SQLite doesn't support extensions. Use Homebrew Python which uses Homebrew SQLite.

## References

- [sqlite-vec documentation](https://alexgarcia.xyz/sqlite-vec/)
- [Ollama](https://ollama.com/)
- [Seed Hypermedia](https://seed.hyper.media/)
