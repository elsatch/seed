# Seed Hybrid Search

Hybrid semantic + keyword search over locally replicated Seed documents using [sqlite-vec](https://alexgarcia.xyz/sqlite-vec/) for fast vector similarity search.

## Features

- **Hybrid retrieval**: Combines vector embeddings (semantic) with FTS5 (keyword) using Reciprocal Rank Fusion
- **Fast vector search**: Uses sqlite-vec for efficient KNN queries
- **Multiple embedding backends**: Ollama (Gemma, nomic-embed-text) or sentence-transformes HuggingFace models (EmbeddingGemma, BGE-M3, Qwen3-Embedding)
- **Indexes documents & comments**: Extracts text from Change and Comment blobs

## Prerequisites

1. **Seed desktop app** installed and run at least once (to create the database)
2. **Python 3.10+**

## Installation

```bash
cd seed/scripts/hybrid-search
./setup.sh
```

This will:

- Create a Python virtual environment
- Install dependencies (sentence-transformers, torch, sqlite-vec)

**Note:** First run will download the embedding model (~600MB for EmbeddingGemma).

## Usage

### Activate environment

```bash
cd seed/scripts/hybrid-search
source .venv/bin/activate
```

### Index content

First run creates the sqlite-vec table for the selected model.

```bash
# Index with default model (EmbeddingGemma)
python embed_indexer.py

# Index with specific model
python embed_indexer.py --model BAAI/bge-m3
python embed_indexer.py --model Qwen/Qwen3-Embedding-0.6B

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

| Platform | Path                                                     |
| -------- | -------------------------------------------------------- |
| Linux    | `~/.config/Seed/daemon/db/db.sqlite`                     |
| macOS    | `~/Library/Application Support/Seed/daemon/db/db.sqlite` |
| Windows  | `%APPDATA%/Seed/daemon/db/db.sqlite`                     |

## Embedding Models

| Model                                                                           | Backend               | Dimensions | Size | Notes                        |
| ------------------------------------------------------------------------------- | --------------------- | ---------- | ---- | ---------------------------- |
| [google/embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m) | sentence-transformers | 768        | 300M | Gemma-based, MRL support     |
| [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)                               | sentence-transformers | 1024       | 568M | Multilingual, 100+ languages |
| [Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)   | sentence-transformers | 1024       | 0.6B | Good balance                 |
| [Qwen/Qwen3-Embedding-8B](https://huggingface.co/Qwen/Qwen3-Embedding-8B)       | sentence-transformers | 4096       | 8B   | Highest quality              |
| `nomic-embed-text`                                                              | Ollama                | 768        |      | **Default**, good balance    |
| `gemma2:2b`                                                                     | Ollama                | 2048       |      | Higher quality, slower       |
| `mxbai-embed-large`                                                             | Ollama                | 1024       |      | Good alternative             |
| `all-minilm`                                                                    | Ollama                | 384        |      | Fast, lower quality          |
| `all-MiniLM-L6-v2`                                                              | sentence-transformers | 384        |      | Fallback option              |

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
│  HuggingFace    │     │    (sqlite-vec)  │     │  HuggingFace    │
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

### Model download slow

First run downloads the model from HuggingFace. This can take a few minutes depending on your connection.

### Out of memory

Try a smaller model:

```bash
python embed_indexer.py --model google/embeddinggemma-300m
```

### Database not found

Ensure Seed desktop app has run at least once to create the database.

## References

- [sqlite-vec documentation](https://alexgarcia.xyz/sqlite-vec/)
- [EmbeddingGemma](https://huggingface.co/google/embeddinggemma-300m)
- [BGE-M3](https://huggingface.co/BAAI/bge-m3)
- [Qwen3-Embedding](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
- [Seed Hypermedia](https://seed.hyper.media/)
