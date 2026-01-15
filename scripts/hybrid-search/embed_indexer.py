"""
embed_indexer.py - Generate embeddings for Seed content

Supports multiple embedding backends:
- Ollama (less overhead, local models)
- Sentence-transformers via HuggingFace(fallback)
google/embeddinggemma-300m (Gemma embeddings)

Manual trigger only - run when you want to index new content.
"""

import os
import sqlite3
import json
import struct
import requests
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple
from pathlib import Path

try:
    import sqlite_vec
    HAS_SQLITE_VEC = True
except ImportError:
    HAS_SQLITE_VEC = False

from seed_decoder import DEFAULT_DB_PATH


# Embedding model configurations (HuggingFace models via sentence-transformers)
EMBEDDING_CONFIGS = {
    # Ollama models
    "gemma2:2b": {"backend": "ollama", "dimensions": 2048},
    "gemma:2b": {"backend": "ollama", "dimensions": 2048},
    "nomic-embed-text": {"backend": "ollama", "dimensions": 768},
    "mxbai-embed-large": {"backend": "ollama", "dimensions": 1024},
    "all-minilm": {"backend": "ollama", "dimensions": 384},

    # Sentence-transformers models
    "google/embeddinggemma-300m": {"backend": "sentence-transformers", "dimensions": 768},
    "BAAI/bge-m3": {"backend": "sentence-transformers", "dimensions": 1024},
    "Qwen/Qwen3-Embedding-0.6B": {"backend": "sentence-transformers", "dimensions": 1024},
    "Qwen/Qwen3-Embedding-8B": {"backend": "sentence-transformers", "dimensions": 4096},
}

# Default: nomic-embed-text (Ollama, 768d, efficient)
DEFAULT_MODEL = "nomic-embed-text"
# Content type to index
CONTENT_TYPES = ['title', 'document', 'comment']


def vec_table_name(model: str, dimensions: int) -> str:
    """Return a SQLite-safe, deterministic vec table name for (model, dimensions)."""
    safe = re.sub(r"[^0-9A-Za-z_]+", "_", model).strip("_")
    if not safe:
        safe = "model"
    return f"vec_embeddings_{safe}_{int(dimensions)}"


def quote_ident(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'

@dataclass
class ContentToEmbed:
    """Content item waiting to be embedded."""
    fts_rowid: int
    text: str
    blob_id: Optional[int] = 0
    block_id: Optional[str] = None
    content_type: Optional[str] = None
    iri: Optional[str] = None


class EmbeddingBackend(ABC):
    """Abstract base class for embedding backends."""

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        pass

    @abstractmethod
    def get_dimensions(self) -> int:
        """Return embedding dimensions."""
        pass


class OllamaBackend(EmbeddingBackend):
    """Ollama embedding backend - supports Gemma and other local models."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model_name = model
        self.base_url = base_url
        self._dimensions = EMBEDDING_CONFIGS.get(model, {}).get("dimensions", 768)

        # Verify Ollama is running and model is available
        self._verify_model()

    def _load_model(self):
        print(f"Model {self.model_name} loaded. Dimensions: {self._dimensions}")
    
    def _verify_model(self):
        """Check if Ollama is running and model is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            models = [m["name"].split(":")[0] for m in response.json().get("models", [])]

            model_base = self.model_name.split(":")[0]
            if model_base not in models and self.model_name not in [m["name"] for m in response.json().get("models", [])]:
                print(f"Warning: Model '{self.model_name}' not found. Available: {models}")
                print(f"Pull it with: ollama pull {self.model_name}")

        except requests.RequestException as e:
            raise ConnectionError(f"Ollama not running at {self.base_url}: {e}")

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Ollama API."""
        embeddings = []

        for text in texts:
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model_name, "prompt": text},
                timeout=30
            )
            response.raise_for_status()
            embedding = response.json()["embedding"]
            embeddings.append(embedding)

            # Update dimensions from actual response
            if len(embedding) != self._dimensions:
                self._dimensions = len(embedding)

        return embeddings

    def get_dimensions(self) -> int:
        return self._dimensions


class SentenceTransformersBackend(EmbeddingBackend):
    """HuggingFace models via sentence-transformers."""

    def __init__(self, model: str):
        self.model_name = model
        self._model = None
        self._dimensions = EMBEDDING_CONFIGS.get(model, {}).get("dimensions", 768)

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, trust_remote_code=True)
            print(f"Model {self.model_name} loaded. Dimensions: {self._dimensions}")
        return self._model

    def embed(self, texts: List[str]) -> List[List[float]]:
        model = self._load_model()
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [e.tolist() for e in embeddings]

    def get_dimensions(self) -> int:
        if self._model is None:
            return self._dimensions
        return self._model.get_sentence_embedding_dimension()


def get_embedding_backend(model: str) -> EmbeddingBackend:
    """Factory function to get appropriate embedding backend."""
    config = EMBEDDING_CONFIGS.get(model, {})
    backend_type = config.get("backend", "ollama")

    if backend_type == "ollama":
        return OllamaBackend(model)
    elif backend_type == "sentence-transformers":
        return SentenceTransformersBackend(model)
    else:
        # Default to Ollama
        return OllamaBackend(model)


class EmbeddingIndexer:
    """Generates and indexes embeddings for Seed content."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        model: str = DEFAULT_MODEL
    ):
        self.db_path = Path(db_path)
        self.model = model
        self._backend: Optional[EmbeddingBackend] = None
        self._vec_table_name_cache: dict[int, str] = {}

    def _get_backend(self) -> EmbeddingBackend:
        """Lazy-load embedding backend."""
        if self._backend is None:
            self._backend = get_embedding_backend(self.model)
        return self._backend

    def _get_connection(self) -> sqlite3.Connection:
        """Get a read-write database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        # Load sqlite-vec extension (optional)
        if HAS_SQLITE_VEC:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)

        return conn

    def _embedding_to_blob(self, embedding: List[float]) -> bytes:
        """Convert embedding list to blob for storage."""
        return struct.pack(f'{len(embedding)}f', *embedding)

    def _blob_to_embedding(self, blob: bytes) -> List[float]:
        """Convert stored blob back to embedding list."""
        count = len(blob) // 4  # float32 = 4 bytes
        return list(struct.unpack(f'{count}f', blob))
    
    def _vec_table_name(self, dimensions: int) -> str:
        """Return a SQLite-safe, deterministic vec table name for (model, dimensions)."""
        cached = self._vec_table_name_cache.get(dimensions)
        if cached is not None:
            return cached

        name = vec_table_name(self.model, dimensions)
        self._vec_table_name_cache[dimensions] = name
        return name

    def _quote_ident(self, ident: str) -> str:
        return quote_ident(ident)

    def _require_sqlite_vec(self):
        if not HAS_SQLITE_VEC:
            raise RuntimeError(
                "sqlite-vec is required for indexing. Install with: pip install sqlite-vec"
            )

    def _ensure_vec_table(self, dimensions: int, force_reset: bool = False) -> Tuple[str, str]:
        """Create or reset the vec table for (model, dimensions)."""
        self._require_sqlite_vec()
        table_name = self._vec_table_name(dimensions)
        table_ident = self._quote_ident(table_name)
        conn = self._get_connection()
        if force_reset:
            conn.execute(f"DROP TABLE IF EXISTS {table_ident}")
            conn.commit()
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_schema
            WHERE type='table' AND name=?
            """,
            (table_name,),
        ).fetchone()
        if row is None:
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE {table_ident} USING vec0(
                    embedding float[{int(dimensions)}]
                )
                """
            )
            conn.commit()
        conn.close()
        return table_name, table_ident

    def get_pending_content(
        self,
        table_ident: str,
        limit: int = 100
    ) -> List[ContentToEmbed]:
        """Return FTS rows that do not yet have vectors."""
        conn = self._get_connection()
        placeholders = ",".join("?" for _ in CONTENT_TYPES)
        query = f"""
        WITH pending AS (
            SELECT rowid
            FROM fts
            WHERE fts.type IN ({placeholders})
              AND length(fts.raw_content) > 3
            EXCEPT
            SELECT rowid
            FROM {table_ident}
        )
        SELECT
            fts.rowid,
            fts.raw_content AS text
        FROM fts
        JOIN pending ON pending.rowid = fts.rowid
        LIMIT ?
        """

        rows = conn.execute(query, (*CONTENT_TYPES, limit)).fetchall()
        conn.close()
        return [
            ContentToEmbed(
                fts_rowid=row["rowid"],
                text=row["text"],
            )
            for row in rows
        ]

    def index_batch(
        self,
        content: List[ContentToEmbed],
        backend: EmbeddingBackend,
        table_ident: str
    ) -> Tuple[int, int]:
        """Generate embeddings for the batch and store them."""
        if not content:
            return 0, 0
        texts = [c.text for c in content]
        try:
            embeddings = backend.embed(texts)
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            return 0, len(content)
        conn = self._get_connection()
        conn.execute("BEGIN")
        cursor = conn.cursor()
        indexed = 0
        skipped = 0
        for item, embedding in zip(content, embeddings):
            embedding_blob = self._embedding_to_blob(embedding)
            cursor.execute(
                f"""
                INSERT OR IGNORE INTO {table_ident}(rowid, embedding)
                VALUES (?, ?)
                """,
                (item.fts_rowid, embedding_blob),
            )
            if cursor.rowcount:
                indexed += 1
            else:
                skipped += 1
        conn.commit()
        conn.close()
        return indexed, skipped

    def run_indexing(
        self,
        batch_size: int = 50,
        max_items: Optional[int] = None,
        force: bool = False
    ) -> Tuple[int, int]:
        """Run indexing on FTS rows missing vectors."""

        backend = self._get_backend()
        dimensions = backend.get_dimensions()
        _, table_ident = self._ensure_vec_table(dimensions, force_reset=force)
        total_indexed = 0
        total_skipped = 0
        while True:
            if max_items and total_indexed >= max_items:
                break
            remaining = batch_size if not max_items else min(batch_size, max_items - total_indexed)
            pending = self.get_pending_content(
                table_ident,
                limit=remaining,
            )
            if not pending:
                break
            print(f"Processing batch of {len(pending)} items...")
            indexed, skipped = self.index_batch(pending, backend, table_ident)
            total_indexed += indexed
            total_skipped += skipped
            print(f"  Indexed: {indexed}, Skipped: {skipped}")
            print(f"  Total: {total_indexed} indexed, {total_skipped} skipped")
        return total_indexed, total_skipped

    def get_stats(self) -> dict:
        """Get vec-table stats for the current model."""
        backend = self._get_backend()
        dimensions = backend.get_dimensions()
        table_name, table_ident = self._ensure_vec_table(dimensions)
        conn = self._get_connection()
        total = conn.execute(
            f"SELECT COUNT(*) AS count FROM {table_ident}"
        ).fetchone()["count"]
        placeholders = ",".join("?" for _ in CONTENT_TYPES)
        pending_query = f"""
            SELECT COUNT(*)
            FROM fts
            WHERE fts.type IN ({placeholders})
              AND length(fts.raw_content) > 3
            EXCEPT
            SELECT
                rowid
            FROM {table_ident}
        """
        pending = conn.execute(pending_query, (*CONTENT_TYPES,)).fetchone()[0]

        conn.close()
        return {
            "total_embeddings": total,
            "pending": pending,
            "current_model": self.model,
            "vec_table": table_name,
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Index Seed content embeddings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index with default model (nomic-embed-text via Ollama)
  python embed_indexer.py

  # Index with BGE-M3 model
  python embed_indexer.py --model BAAI/bge-m3

  # Index with Qwen3 Embedding
  python embed_indexer.py --model Qwen/Qwen3-Embedding-0.6B

  # Index only titles and comments
  python embed_indexer.py --types title comment

  # Show statistics only
  python embed_indexer.py --stats

Available models:
  Ollama (local):
    - nomic-embed-text (768d, default)
    - gemma2:2b (2048d)
    - mxbai-embed-large (1024d)
    - all-minilm (384d)

  Sentence-transformers via HuggingFace:
  - google/embeddinggemma-300m (768d, Gemma-based)
  - BAAI/bge-m3 (1024d, multilingual)
  - Qwen/Qwen3-Embedding-0.6B (1024d)
  - Qwen/Qwen3-Embedding-8B (4096d, high quality)
        """
    )

    parser.add_argument("--db", type=Path, default=Path(os.environ.get("SEED_DB_PATH", DEFAULT_DB_PATH)),
                        help="Path to SQLite database")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Embedding model (default: {DEFAULT_MODEL})")
    parser.add_argument("--batch-size", type=int, default=100,
                        help="Batch size for processing")
    parser.add_argument("--max", type=int, default=None,
                        help="Maximum items to index")
    parser.add_argument("--stats", action="store_true",
                        help="Show statistics only")
    parser.add_argument("--force", action="store_true",
                        help="Drop and rebuild the vec table before indexing")

    args = parser.parse_args()

    indexer = EmbeddingIndexer(args.db, args.model)

    if args.stats:
        stats = indexer.get_stats()
        print(json.dumps(stats, indent=2))
        return

    print(f"Indexing with model: {args.model}")
    print(f"Database: {args.db}")
    print()

    indexed, skipped = indexer.run_indexing(
        batch_size=args.batch_size,
        max_items=args.max,
        force=args.force,
    )

    print()
    print(f"Indexing complete!")
    print(f"  Total indexed: {indexed}")
    print(f"  Total skipped: {skipped}")

    # Show final stats
    print()
    print("Current statistics:")
    stats = indexer.get_stats()
    print(f"  Total embeddings: {stats['total_embeddings']}")
    print(f"  Pending: {stats['pending']}")


if __name__ == "__main__":
    main()
