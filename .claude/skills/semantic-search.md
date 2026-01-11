---
name: semantic-search
description: Semantic search over locally replicated Seed documents. Use when finding content by meaning, related documents, or exploring topics.
---

# Seed Semantic Search

Hybrid retrieval combining sqlite-vec (vector KNN) + FTS5 (keyword) over local Seed database.

## Prerequisites

```bash
# Ollama running with embedding model
ollama serve
ollama pull nomic-embed-text
```

## Quick Start

```bash
cd ~/seed/scripts/hybrid-search
./setup.sh  # First time only

source .venv/bin/activate

# Index content (manual trigger)
python embed_indexer.py

# Search
python hybrid_search.py "your query"
```

## Commands

### Index Content
```bash
python embed_indexer.py                    # Index all
python embed_indexer.py --model gemma2:2b  # Use Gemma
python embed_indexer.py --types title      # Only titles
python embed_indexer.py --stats            # Show stats
```

### Search
```bash
python hybrid_search.py "query"                    # Hybrid (default)
python hybrid_search.py "query" --mode semantic    # Semantic only
python hybrid_search.py "query" --mode keyword     # Keyword only
python hybrid_search.py "query" --format json      # JSON output
python hybrid_search.py "query" --weight 0.7       # More semantic
```

## Database Locations

| Platform | Path |
|----------|------|
| Linux | `~/.config/Seed/daemon/db/db.sqlite` |
| macOS | `~/Library/Application Support/Seed/daemon/db/db.sqlite` |

## Models

| Model | Dimensions | Notes |
|-------|------------|-------|
| `nomic-embed-text` | 768 | Recommended |
| `gemma2:2b` | 2048 | Higher quality |
| `mxbai-embed-large` | 1024 | Good balance |

## Output

Text mode:
```
1. [document] hm://z6Mk.../path
   Score: 0.0234 (sem:0.823 kw:0.156)
   Content snippet...
```

JSON mode returns structured data with IRI, scores, timestamps, and author info.
