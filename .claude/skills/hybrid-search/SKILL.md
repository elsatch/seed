---
name: hybrid-search
description: Hybrid search (semantic + keyword) over local Seed documents. Use when finding content by meaning, related documents, or exploring topics.
---

# Seed Hybrid Search

Hybrid retrieval combining sqlite-vec (vector KNN) + FTS5 (keyword) 
over local Seed database.
Uses sentence-transformers (HuggingFace) by default, or Ollama with `--ollama`.

## Quick Start

The database path should be in the `SEED_DB_PATH` env variable. 
If that variable is not set, ask the user where the db is located
and try to find the db.sqlite there, then export that path into `SEED_DB_PATH`
```bash
cd ~/seed/scripts/hybrid-search
source .venv/bin/activate
./setup.sh  # First time only


# Index content (first run may download model)
python embed_indexer.py

# Search
python hybrid_search.py "your query" 
```

## Commands

### Index Content
```bash
python embed_indexer.py                              # Default (sentence-transformers)
python embed_indexer.py --model BAAI/bge-m3          # HuggingFace model
python embed_indexer.py --model Qwen/Qwen3-Embedding-0.6B  # HuggingFace model
python embed_indexer.py --ollama --model nomic-embed-text  # Ollama backend (auto-pull)
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

| Platform |                         Path                            |
|----------|---------------------------------------------------------|
| Linux    | `~/.config/Seed/daemon/db/db.sqlite`                    |
| macOS    | `~/Library/Application Support/Seed/daemon/db/db.sqlite`|

## Models

This tool does not enforce a fixed list of models. Use any compatible model name:

- **Sentence-transformers**: Any model available on HuggingFace supported by `sentence-transformers`.
- **Ollama**: Any model name supported by Ollama; it will be pulled automatically when indexing.

In order to work with gated models, the user must define `HF_TOKEN` env var
containing the Hugging Face token. The user must log in to HuggingFace and
accept the license of the gated model before it can be used.

## Output

Text mode:
```
1. [document] hm://z6Mk.../path
   Score: 0.0234 (sem:0.823 kw:0.156)
   Content snippet...
```

JSON mode returns structured data with IRI, scores, timestamps, and author info.
