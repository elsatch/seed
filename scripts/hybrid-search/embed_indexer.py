"""
embed_indexer.py - Generate embeddings for Seed content

Supports multiple embedding backends:
- Ollama (recommended for Gemma models)
- Sentence-transformers (fallback)

Manual trigger only - run when you want to index new content.
"""

import sqlite3
import hashlib
import json
import struct
import requests
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple
from pathlib import Path

from seed_decoder import SeedBlobDecoder, DEFAULT_DB_PATH


# Embedding model configurations
EMBEDDING_CONFIGS = {
    # Ollama models
    "gemma2:2b": {"backend": "ollama", "dimensions": 2048},
    "gemma:2b": {"backend": "ollama", "dimensions": 2048},
    "nomic-embed-text": {"backend": "ollama", "dimensions": 768},
    "mxbai-embed-large": {"backend": "ollama", "dimensions": 1024},
    "all-minilm": {"backend": "ollama", "dimensions": 384},
    # Sentence-transformers models
    "all-MiniLM-L6-v2": {"backend": "sentence-transformers", "dimensions": 384},
    "all-mpnet-base-v2": {"backend": "sentence-transformers", "dimensions": 768},
}

DEFAULT_MODEL = "nomic-embed-text"  # Good balance of quality and speed


@dataclass
class ContentToEmbed:
    """Content item waiting to be embedded."""
    fts_rowid: int
    blob_id: int
    block_id: str
    content_type: str
    text: str
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
        self.model = model
        self.base_url = base_url
        self._dimensions = EMBEDDING_CONFIGS.get(model, {}).get("dimensions", 768)

        # Verify Ollama is running and model is available
        self._verify_model()

    def _verify_model(self):
        """Check if Ollama is running and model is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            models = [m["name"].split(":")[0] for m in response.json().get("models", [])]

            model_base = self.model.split(":")[0]
            if model_base not in models and self.model not in [m["name"] for m in response.json().get("models", [])]:
                print(f"Warning: Model '{self.model}' not found. Available: {models}")
                print(f"Pull it with: ollama pull {self.model}")

        except requests.RequestException as e:
            raise ConnectionError(f"Ollama not running at {self.base_url}: {e}")

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Ollama API."""
        embeddings = []

        for text in texts:
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
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
    """Sentence-transformers backend (fallback)."""

    def __init__(self, model: str):
        self.model_name = model
        self._model = None
        self._dimensions = EMBEDDING_CONFIGS.get(model, {}).get("dimensions", 384)

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: List[str]) -> List[List[float]]:
        model = self._load_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return [e.tolist() for e in embeddings]

    def get_dimensions(self) -> int:
        return self._dimensions


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
        self.decoder = SeedBlobDecoder(db_path)
        self._backend: Optional[EmbeddingBackend] = None

    def _get_backend(self) -> EmbeddingBackend:
        """Lazy-load embedding backend."""
        if self._backend is None:
            self._backend = get_embedding_backend(self.model)
        return self._backend

    def _get_connection(self) -> sqlite3.Connection:
        """Get a read-write database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _compute_content_hash(self, text: str) -> bytes:
        """Compute SHA256 hash of text content."""
        return hashlib.sha256(text.encode('utf-8')).digest()

    def _embedding_to_blob(self, embedding: List[float]) -> bytes:
        """Convert embedding list to blob for storage."""
        return struct.pack(f'{len(embedding)}f', *embedding)

    def _blob_to_embedding(self, blob: bytes) -> List[float]:
        """Convert stored blob back to embedding list."""
        count = len(blob) // 4  # float32 = 4 bytes
        return list(struct.unpack(f'{count}f', blob))

    def ensure_schema(self):
        """Ensure embeddings table exists."""
        conn = self._get_connection()

        # Check if table exists
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='embeddings'
        """)

        if not cursor.fetchone():
            print("Creating embeddings table...")
            migration_path = Path(__file__).parent / "migrations" / "001_create_embeddings.sql"
            with open(migration_path) as f:
                # Execute each statement separately (skip VSS for now)
                for statement in f.read().split(';'):
                    statement = statement.strip()
                    if statement and not statement.startswith('--') and 'vss0' not in statement.lower():
                        conn.execute(statement)
            conn.commit()
            print("Embeddings table created.")

        conn.close()

    def get_pending_content(
        self,
        content_types: List[str] = None,
        limit: int = 100
    ) -> List[ContentToEmbed]:
        """Get FTS content that needs embedding."""
        if content_types is None:
            content_types = ['title', 'document', 'comment']

        results = self.decoder.get_unembedded_fts_content(
            model=self.model,
            content_types=content_types,
            limit=limit
        )

        return [
            ContentToEmbed(
                fts_rowid=r["rowid"],
                blob_id=r["blob_id"],
                block_id=r["block_id"] or "",
                content_type=r["type"],
                text=r["raw_content"],
                iri=r.get("iri")
            )
            for r in results
            if r["raw_content"] and len(r["raw_content"]) > 10
        ]

    def index_batch(self, content: List[ContentToEmbed]) -> Tuple[int, int]:
        """
        Generate embeddings and store them.

        Returns (indexed_count, skipped_count)
        """
        if not content:
            return 0, 0

        backend = self._get_backend()
        dimensions = backend.get_dimensions()

        # Generate embeddings
        texts = [c.text for c in content]
        try:
            embeddings = backend.embed(texts)
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            return 0, len(content)

        conn = self._get_connection()
        cursor = conn.cursor()

        indexed = 0
        skipped = 0

        for item, embedding in zip(content, embeddings):
            content_hash = self._compute_content_hash(item.text)

            # Check if already exists
            cursor.execute("""
                SELECT id FROM embeddings
                WHERE content_hash = ? AND model = ?
            """, [content_hash, self.model])

            if cursor.fetchone():
                skipped += 1
                continue

            # Insert embedding
            embedding_blob = self._embedding_to_blob(embedding)

            cursor.execute("""
                INSERT INTO embeddings
                (fts_rowid, blob_id, block_id, content_type,
                 content_hash, embedding, model, dimensions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                item.fts_rowid,
                item.blob_id,
                item.block_id,
                item.content_type,
                content_hash,
                embedding_blob,
                self.model,
                dimensions
            ])

            indexed += 1

        conn.commit()
        conn.close()
        return indexed, skipped

    def run_indexing(
        self,
        content_types: List[str] = None,
        batch_size: int = 50,
        max_items: Optional[int] = None
    ) -> Tuple[int, int]:
        """
        Run indexing on unembedded content.

        Args:
            content_types: Types to index (default: title, document, comment)
            batch_size: Items per batch
            max_items: Maximum items to index (None = all)

        Returns (total_indexed, total_skipped)
        """
        if content_types is None:
            content_types = ['title', 'document', 'comment']

        # Ensure schema exists
        self.ensure_schema()

        total_indexed = 0
        total_skipped = 0

        while True:
            # Check limit
            if max_items and total_indexed >= max_items:
                break

            # Get pending content
            remaining = batch_size
            if max_items:
                remaining = min(batch_size, max_items - total_indexed)

            pending = self.get_pending_content(
                content_types=content_types,
                limit=remaining
            )

            if not pending:
                break

            print(f"Processing batch of {len(pending)} items...")

            indexed, skipped = self.index_batch(pending)
            total_indexed += indexed
            total_skipped += skipped

            print(f"  Indexed: {indexed}, Skipped: {skipped}")
            print(f"  Total: {total_indexed} indexed, {total_skipped} skipped")

        return total_indexed, total_skipped

    def get_stats(self) -> dict:
        """Get indexing statistics."""
        conn = self._get_connection()

        # Total embeddings
        total = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]

        # By model
        by_model = conn.execute("""
            SELECT model, COUNT(*) as count
            FROM embeddings
            GROUP BY model
        """).fetchall()

        # By type
        by_type = conn.execute("""
            SELECT content_type, COUNT(*) as count
            FROM embeddings
            GROUP BY content_type
        """).fetchall()

        # Pending (unembedded FTS entries for current model)
        pending = conn.execute("""
            SELECT COUNT(*)
            FROM fts_index fi
            LEFT JOIN embeddings e ON e.fts_rowid = fi.rowid AND e.model = ?
            WHERE e.id IS NULL AND fi.type IN ('title', 'document', 'comment')
        """, [self.model]).fetchone()[0]

        conn.close()

        return {
            "total_embeddings": total,
            "by_model": {r["model"]: r["count"] for r in by_model},
            "by_type": {r["content_type"]: r["count"] for r in by_type},
            "pending": pending,
            "current_model": self.model
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

  # Index with Gemma model
  python embed_indexer.py --model gemma2:2b

  # Index only titles and comments
  python embed_indexer.py --types title comment

  # Show statistics only
  python embed_indexer.py --stats

Available models:
  Ollama (local):
    - nomic-embed-text (768d, recommended)
    - gemma2:2b (2048d)
    - mxbai-embed-large (1024d)
    - all-minilm (384d)

  Sentence-transformers:
    - all-MiniLM-L6-v2 (384d)
    - all-mpnet-base-v2 (768d)
        """
    )

    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help="Path to SQLite database")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Embedding model (default: {DEFAULT_MODEL})")
    parser.add_argument("--types", nargs="+", default=["title", "document", "comment"],
                        help="Content types to index")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Batch size for processing")
    parser.add_argument("--max", type=int, default=None,
                        help="Maximum items to index")
    parser.add_argument("--stats", action="store_true",
                        help="Show statistics only")

    args = parser.parse_args()

    indexer = EmbeddingIndexer(args.db, args.model)

    if args.stats:
        stats = indexer.get_stats()
        print(json.dumps(stats, indent=2))
        return

    print(f"Indexing with model: {args.model}")
    print(f"Content types: {args.types}")
    print(f"Database: {args.db}")
    print()

    indexed, skipped = indexer.run_indexing(
        content_types=args.types,
        batch_size=args.batch_size,
        max_items=args.max
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
