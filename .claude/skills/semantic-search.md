---
name: semantic-search
description: Semantic search over locally replicated Seed documents using Gemma embeddings. Use when finding content by meaning, related documents, or exploring topics.
---

# Seed Semantic Search

Hybrid retrieval combining sqlite-vec (vector KNN) + FTS5 (keyword) over local Seed database.
Uses HuggingFace models with EmbeddingGemma as default.

## Quick Start

```bash
cd ~/seed/scripts/hybrid-search
./setup.sh  # First time only

source .venv/bin/activate

# Index content (first run downloads model)
python embed_indexer.py

# Search
python hybrid_search.py "your query"
```

## Commands

### Index Content
```bash
python embed_indexer.py                              # Default (EmbeddingGemma)
python embed_indexer.py --model BAAI/bge-m3          # BGE-M3
python embed_indexer.py --model Qwen/Qwen3-Embedding-0.6B  # Qwen3
python embed_indexer.py --types title                # Only titles
python embed_indexer.py --stats                      # Show stats
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

## Models (HuggingFace)

| Model | Dimensions | Notes |
|-------|------------|-------|
| `google/embeddinggemma-300m` | 768 | **Default**, Gemma-based |
| `BAAI/bge-m3` | 1024 | Multilingual |
| `Qwen/Qwen3-Embedding-0.6B` | 1024 | Good balance |
| `Qwen/Qwen3-Embedding-8B` | 4096 | High quality |

## Output

Text mode:
```
1. [document] hm://z6Mk.../path
   Score: 0.0234 (sem:0.823 kw:0.156)
   Content snippet...
```

JSON mode returns structured data with IRI, scores, timestamps, and author info.
