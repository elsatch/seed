---
name: semantic-search
description: Semantic search over locally replicated Seed documents. Use when finding content by meaning, related documents, or exploring topics.
---

# Seed Semantic Search

Hybrid retrieval combining vector embeddings + FTS5 keyword search over local Seed database.

## Prerequisites

Ensure Ollama is running with an embedding model:
```bash
# Check Ollama status
ollama list

# Pull recommended model if needed
ollama pull nomic-embed-text
```

## Quick Start

```bash
cd ~/seed/scripts/hybrid-search
source .venv/bin/activate  # If venv exists

# First time: run setup
./setup.sh

# Index content (manual trigger)
python embed_indexer.py

# Search
python hybrid_search.py "your query"
```

## Commands

### Index New Content
```bash
# Index all unembedded content
python embed_indexer.py

# Index with specific model
python embed_indexer.py --model gemma2:2b

# Index only titles
python embed_indexer.py --types title

# Check stats
python embed_indexer.py --stats
```

### Search
```bash
# Hybrid search (recommended)
python hybrid_search.py "query"

# Semantic only
python hybrid_search.py "query" --mode semantic

# Keyword only
python hybrid_search.py "query" --mode keyword

# JSON output
python hybrid_search.py "query" --format json

# Adjust semantic weight (0.7 = more semantic)
python hybrid_search.py "query" --weight 0.7

# Search specific types
python hybrid_search.py "query" --types title document
```

## Embedding Models

| Model | Backend | Dimensions | Notes |
|-------|---------|------------|-------|
| `nomic-embed-text` | Ollama | 768 | Recommended default |
| `gemma2:2b` | Ollama | 2048 | Higher quality |
| `mxbai-embed-large` | Ollama | 1024 | Good balance |
| `all-MiniLM-L6-v2` | sentence-transformers | 384 | Fallback |

## Database

Location: `~/.local/share/seed-daemon/db/db.sqlite`

Indexes both public and authenticated content from:
- Document text (type: document)
- Document titles (type: title)
- Comments (type: comment)

## Output Format

Text mode shows ranked results:
```
1. [document] hm://z6Mk.../path
   Score: 0.0234 (sem:0.823 kw:0.156)
   Content snippet...
```

JSON mode returns structured data with all metadata.
