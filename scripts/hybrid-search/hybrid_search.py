"""
hybrid_search.py - Hybrid semantic + keyword search for Seed

Combines:
1. Vector similarity search (cosine similarity on embeddings)
2. FTS5 full-text search (BM25 ranking)

Uses Reciprocal Rank Fusion (RRF) to combine results.
"""

import sqlite3
import json
import struct
import math
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from seed_decoder import DEFAULT_DB_PATH
from embed_indexer import (
    EmbeddingIndexer,
    get_embedding_backend,
    DEFAULT_MODEL,
    EMBEDDING_CONFIGS
)


@dataclass
class SearchResult:
    """Search result with scores and metadata."""
    iri: str
    blob_id: int
    block_id: str
    content_type: str
    text_snippet: str
    version: str

    # Scores (0-1 range)
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    combined_score: float = 0.0

    # Metadata
    timestamp: Optional[int] = None
    author_principal: Optional[str] = None


class HybridSearch:
    """Performs hybrid semantic + keyword search."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        model: str = DEFAULT_MODEL,
        rrf_k: int = 60
    ):
        self.db_path = Path(db_path)
        self.model = model
        self.rrf_k = rrf_k  # RRF constant
        self._backend = None

    def _get_backend(self):
        """Lazy-load embedding backend."""
        if self._backend is None:
            self._backend = get_embedding_backend(self.model)
        return self._backend

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _embedding_to_list(self, blob: bytes) -> List[float]:
        """Convert blob to embedding list."""
        count = len(blob) // 4
        return list(struct.unpack(f'{count}f', blob))

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def semantic_search(
        self,
        query: str,
        limit: int = 20,
        content_types: List[str] = None
    ) -> List[Dict]:
        """
        Perform semantic search using vector similarity.

        Since sqlite-vss may not be available, we use brute-force
        cosine similarity (fine for <100k embeddings).
        """
        if content_types is None:
            content_types = ['title', 'document', 'comment']

        # Generate query embedding
        backend = self._get_backend()
        query_embedding = backend.embed([query])[0]

        conn = self._get_connection()

        # Get all embeddings of specified types
        placeholders = ",".join("?" * len(content_types))
        query_sql = f"""
        SELECT
            e.id,
            e.fts_rowid,
            e.blob_id,
            e.block_id,
            e.content_type,
            e.embedding,
            fi.version,
            fi.ts,
            f.raw_content,
            r.iri,
            pk.principal
        FROM embeddings e
        JOIN fts_index fi ON fi.rowid = e.fts_rowid
        JOIN fts f ON f.rowid = fi.rowid
        LEFT JOIN structural_blobs sb ON sb.id = e.blob_id
        LEFT JOIN resources r ON r.id = sb.resource
        LEFT JOIN public_keys pk ON pk.id = sb.author
        WHERE e.model = ?
        AND e.content_type IN ({placeholders})
        """

        params = [self.model] + content_types
        cursor = conn.execute(query_sql, params)

        # Compute similarities
        results = []
        for row in cursor:
            embedding = self._embedding_to_list(row["embedding"])
            similarity = self._cosine_similarity(query_embedding, embedding)

            results.append({
                "iri": row["iri"] or "",
                "blob_id": row["blob_id"],
                "block_id": row["block_id"],
                "content_type": row["content_type"],
                "text_snippet": row["raw_content"][:300] if row["raw_content"] else "",
                "version": row["version"] or "",
                "semantic_score": (similarity + 1) / 2,  # Normalize to 0-1
                "timestamp": row["ts"],
                "author_principal": row["principal"].hex() if row["principal"] else None
            })

        conn.close()

        # Sort by similarity and take top results
        results.sort(key=lambda x: x["semantic_score"], reverse=True)
        return results[:limit]

    def keyword_search(
        self,
        query: str,
        limit: int = 20,
        content_types: List[str] = None
    ) -> List[Dict]:
        """
        Perform keyword search using FTS5.
        """
        if content_types is None:
            content_types = ['title', 'document', 'comment']

        conn = self._get_connection()

        # Clean query for FTS5
        clean_query = ''.join(c for c in query if c.isalnum() or c.isspace())
        clean_query = ' '.join(clean_query.split())  # Normalize whitespace

        if not clean_query:
            return []

        # FTS5 query with wildcards
        fts_query = ' '.join(f'{word}*' for word in clean_query.split())

        placeholders = ",".join("?" * len(content_types))
        query_sql = f"""
        SELECT
            fi.rowid,
            fi.blob_id,
            fi.block_id,
            fi.type as content_type,
            fi.version,
            fi.ts,
            f.raw_content,
            r.iri,
            pk.principal,
            bm25(fts) as rank
        FROM fts f
        JOIN fts_index fi ON f.rowid = fi.rowid
        LEFT JOIN structural_blobs sb ON sb.id = fi.blob_id
        LEFT JOIN resources r ON r.id = sb.resource
        LEFT JOIN public_keys pk ON pk.id = sb.author
        WHERE fts MATCH ?
        AND fi.type IN ({placeholders})
        ORDER BY rank
        LIMIT ?
        """

        params = [fts_query] + content_types + [limit * 2]

        try:
            cursor = conn.execute(query_sql, params)
        except sqlite3.OperationalError as e:
            print(f"FTS query error: {e}")
            conn.close()
            return []

        results = []
        for row in cursor:
            # BM25 returns negative scores, lower is better
            # Normalize to 0-1 range
            normalized_score = 1.0 / (1.0 + abs(row["rank"]))

            results.append({
                "iri": row["iri"] or "",
                "blob_id": row["blob_id"],
                "block_id": row["block_id"],
                "content_type": row["content_type"],
                "text_snippet": row["raw_content"][:300] if row["raw_content"] else "",
                "version": row["version"] or "",
                "keyword_score": normalized_score,
                "timestamp": row["ts"],
                "author_principal": row["principal"].hex() if row["principal"] else None
            })

        conn.close()
        return results[:limit]

    def hybrid_search(
        self,
        query: str,
        limit: int = 20,
        content_types: List[str] = None,
        semantic_weight: float = 0.5
    ) -> List[SearchResult]:
        """
        Perform hybrid search combining semantic and keyword search.

        Uses Reciprocal Rank Fusion (RRF) to combine results.

        Args:
            query: Search query
            limit: Max results
            content_types: Types to search
            semantic_weight: Weight for semantic vs keyword (0-1)
        """
        if content_types is None:
            content_types = ['title', 'document', 'comment']

        # Get results from both methods
        semantic_results = self.semantic_search(query, limit * 2, content_types)
        keyword_results = self.keyword_search(query, limit * 2, content_types)

        # Build result map keyed by (iri, block_id)
        result_map: Dict[Tuple[str, str], Dict] = {}

        # Process semantic results
        for rank, result in enumerate(semantic_results):
            key = (result["iri"], result["block_id"])
            if key not in result_map:
                result_map[key] = result.copy()
                result_map[key]["semantic_rank"] = rank + 1
                result_map[key]["keyword_rank"] = None
            else:
                result_map[key]["semantic_rank"] = rank + 1
                result_map[key]["semantic_score"] = result["semantic_score"]

        # Process keyword results
        for rank, result in enumerate(keyword_results):
            key = (result["iri"], result["block_id"])
            if key not in result_map:
                result_map[key] = result.copy()
                result_map[key]["keyword_rank"] = rank + 1
                result_map[key]["semantic_rank"] = None
                result_map[key]["semantic_score"] = 0.0
            else:
                result_map[key]["keyword_rank"] = rank + 1
                result_map[key]["keyword_score"] = result["keyword_score"]

        # Calculate RRF scores
        for key, result in result_map.items():
            semantic_rrf = 0.0
            keyword_rrf = 0.0

            if result.get("semantic_rank"):
                semantic_rrf = 1.0 / (self.rrf_k + result["semantic_rank"])
            if result.get("keyword_rank"):
                keyword_rrf = 1.0 / (self.rrf_k + result["keyword_rank"])

            # Weighted combination
            result["combined_score"] = (
                semantic_weight * semantic_rrf +
                (1 - semantic_weight) * keyword_rrf
            )

        # Sort by combined score
        sorted_results = sorted(
            result_map.values(),
            key=lambda x: x["combined_score"],
            reverse=True
        )

        # Convert to SearchResult objects
        search_results = []
        for r in sorted_results[:limit]:
            search_results.append(SearchResult(
                iri=r.get("iri", ""),
                blob_id=r["blob_id"],
                block_id=r.get("block_id", ""),
                content_type=r["content_type"],
                text_snippet=r.get("text_snippet", ""),
                version=r.get("version", ""),
                semantic_score=r.get("semantic_score", 0.0),
                keyword_score=r.get("keyword_score", 0.0),
                combined_score=r["combined_score"],
                timestamp=r.get("timestamp"),
                author_principal=r.get("author_principal")
            ))

        return search_results

    def search(
        self,
        query: str,
        mode: str = "hybrid",
        limit: int = 20,
        content_types: List[str] = None,
        semantic_weight: float = 0.5,
        output_format: str = "json"
    ) -> str:
        """
        Main search entry point.

        Args:
            query: Search query
            mode: 'hybrid', 'semantic', or 'keyword'
            limit: Max results
            content_types: Types to search
            semantic_weight: Weight for hybrid mode
            output_format: 'json' or 'text'
        """
        if content_types is None:
            content_types = ['title', 'document', 'comment']

        if mode == "semantic":
            results = self.semantic_search(query, limit, content_types)
            results = [SearchResult(
                iri=r.get("iri", ""),
                blob_id=r["blob_id"],
                block_id=r.get("block_id", ""),
                content_type=r["content_type"],
                text_snippet=r.get("text_snippet", ""),
                version=r.get("version", ""),
                semantic_score=r.get("semantic_score", 0.0),
                combined_score=r.get("semantic_score", 0.0),
                timestamp=r.get("timestamp"),
                author_principal=r.get("author_principal")
            ) for r in results]

        elif mode == "keyword":
            results = self.keyword_search(query, limit, content_types)
            results = [SearchResult(
                iri=r.get("iri", ""),
                blob_id=r["blob_id"],
                block_id=r.get("block_id", ""),
                content_type=r["content_type"],
                text_snippet=r.get("text_snippet", ""),
                version=r.get("version", ""),
                keyword_score=r.get("keyword_score", 0.0),
                combined_score=r.get("keyword_score", 0.0),
                timestamp=r.get("timestamp"),
                author_principal=r.get("author_principal")
            ) for r in results]

        else:  # hybrid
            results = self.hybrid_search(
                query, limit, content_types, semantic_weight
            )

        if output_format == "json":
            return json.dumps([asdict(r) for r in results], indent=2)
        else:
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. [{r.content_type}] {r.iri or 'N/A'}")
                lines.append(f"   Score: {r.combined_score:.4f} (sem:{r.semantic_score:.3f} kw:{r.keyword_score:.3f})")
                snippet = r.text_snippet[:100].replace('\n', ' ')
                lines.append(f"   {snippet}...")
                lines.append("")
            return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Hybrid search for Seed content",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Hybrid search (default)
  python hybrid_search.py "machine learning concepts"

  # Semantic-only search
  python hybrid_search.py "neural networks" --mode semantic

  # Keyword-only search
  python hybrid_search.py "exact phrase" --mode keyword

  # Search only titles
  python hybrid_search.py "introduction" --types title

  # Adjust semantic weight (0.7 = more semantic, 0.3 = more keyword)
  python hybrid_search.py "topic" --weight 0.7
        """
    )

    parser.add_argument("query", help="Search query")
    parser.add_argument("--mode", choices=["hybrid", "semantic", "keyword"],
                        default="hybrid", help="Search mode")
    parser.add_argument("--limit", type=int, default=20, help="Max results")
    parser.add_argument("--types", nargs="+", default=["title", "document", "comment"],
                        help="Content types to search")
    parser.add_argument("--weight", type=float, default=0.5,
                        help="Semantic weight for hybrid mode (0-1)")
    parser.add_argument("--format", choices=["json", "text"], default="text",
                        help="Output format")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help="Database path")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="Embedding model")

    args = parser.parse_args()

    search = HybridSearch(args.db, args.model)

    output = search.search(
        args.query,
        mode=args.mode,
        limit=args.limit,
        content_types=args.types,
        semantic_weight=args.weight,
        output_format=args.format
    )

    print(output)


if __name__ == "__main__":
    main()
