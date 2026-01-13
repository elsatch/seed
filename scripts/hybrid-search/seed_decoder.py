"""
seed_decoder.py - Decode Seed blobs from SQLite database

Decodes Zstd-compressed DAG-CBOR blobs from the Seed database.
Focuses on Change and Comment blobs for text extraction.
"""

import sqlite3
import zstandard
import cbor2
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Iterator
from pathlib import Path
import os
import platform


def get_default_db_path() -> Path:
    """Get platform-specific default database path."""
    if platform.system() == "Darwin":
        return Path.home() / "Library/Application Support/Seed/daemon/db/db.sqlite"
    elif platform.system() == "Windows":
        return Path(os.environ.get("APPDATA", "")) / "Seed/daemon/db/db.sqlite"
    else:  # Linux and others
        return Path.home() / ".config/Seed/daemon/db/db.sqlite"


DEFAULT_DB_PATH = get_default_db_path()


@dataclass
class ExtractedContent:
    """Represents extracted text content from a blob."""
    blob_id: int
    block_id: str
    content_type: str  # 'title', 'document', 'comment'
    text: str
    timestamp: Optional[int] = None
    author_id: Optional[int] = None
    resource_iri: Optional[str] = None


@dataclass
class DecodedChange:
    """Decoded Change blob structure."""
    blob_id: int
    signer: bytes
    timestamp: int  # Unix milliseconds
    genesis: Optional[bytes]
    deps: List[bytes]
    depth: int
    ops: List[Dict[str, Any]]

    def extract_text(self) -> List[ExtractedContent]:
        """Extract text content from ReplaceBlock operations."""
        content = []
        for op in self.ops:
            op_type = op.get("@type") or op.get("type", "")

            if op_type == "ReplaceBlock":
                block = op.get("b") or op.get("block", {})
                text = block.get("t") or block.get("text", "")
                block_id = block.get("id") or block.get("iD") or ""

                if text and text.strip():
                    content.append(ExtractedContent(
                        blob_id=self.blob_id,
                        block_id=block_id,
                        content_type="document",
                        text=text.strip(),
                        timestamp=self.timestamp
                    ))

            elif op_type in ("SetKey", "SetAttribute", "SetAttributes"):
                key = op.get("k") or op.get("key", "")
                value = op.get("v") or op.get("value", "")

                if key in ("title", "name") and isinstance(value, str) and value.strip():
                    content.append(ExtractedContent(
                        blob_id=self.blob_id,
                        block_id="",
                        content_type="title",
                        text=value.strip(),
                        timestamp=self.timestamp
                    ))

        return content


@dataclass
class DecodedComment:
    """Decoded Comment blob structure."""
    blob_id: int
    signer: bytes
    timestamp: int
    tsid: str
    space: Optional[bytes]
    path: str
    body: List[Dict[str, Any]]

    def extract_text(self) -> List[ExtractedContent]:
        """Extract text content from comment body blocks."""
        content = []

        def extract_from_blocks(blocks: List[Dict], parent_id: str = ""):
            for i, block in enumerate(blocks):
                text = block.get("t") or block.get("text", "")
                block_id = block.get("id") or block.get("iD") or f"{parent_id}_{i}"

                if text and text.strip():
                    content.append(ExtractedContent(
                        blob_id=self.blob_id,
                        block_id=block_id,
                        content_type="comment",
                        text=text.strip(),
                        timestamp=self.timestamp
                    ))

                # Recurse into children
                children = block.get("c") or block.get("children", [])
                if children:
                    extract_from_blocks(children, block_id)

        extract_from_blocks(self.body)
        return content


class SeedBlobDecoder:
    """Decodes Seed blobs from SQLite database."""

    # DAG-CBOR codec
    CODEC_DAG_CBOR = 0x71
    CODEC_DAG_PB = 0x70
    CODEC_RAW = 0x55

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.decompressor = zstandard.ZstdDecompressor()

        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get a read-only database connection."""
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _decompress(self, data: bytes, original_size: int) -> bytes:
        """Decompress zstd-compressed data."""
        if not data or original_size <= 0:
            return b""
        try:
            return self.decompressor.decompress(data, max_output_size=original_size)
        except Exception:
            # Try without size limit
            return self.decompressor.decompress(data)

    def _decode_cbor(self, data: bytes) -> Dict[str, Any]:
        """Decode DAG-CBOR data."""
        try:
            return cbor2.loads(data)
        except Exception as e:
            raise ValueError(f"CBOR decode failed: {e}")

    def decode_blob(self, data: bytes, size: int, codec: int) -> Optional[Dict[str, Any]]:
        """Decompress and decode a blob."""
        if codec != self.CODEC_DAG_CBOR:
            return None

        decompressed = self._decompress(data, size)
        return self._decode_cbor(decompressed)

    def get_content_blobs(
        self,
        blob_types: List[str] = None,
        include_public: bool = True,
        include_private: bool = True,
        limit: int = 1000,
        offset: int = 0
    ) -> Iterator[Dict[str, Any]]:
        """
        Fetch and decode content blobs (Changes and Comments).

        Args:
            blob_types: Filter by types (default: ['Change', 'Comment'])
            include_public: Include public blobs (space=0)
            include_private: Include private/space blobs
            limit: Max blobs to fetch per batch
            offset: Pagination offset
        """
        if blob_types is None:
            blob_types = ['Change', 'Comment']

        conn = self._get_connection()

        # Build visibility filter
        if include_public and include_private:
            visibility_filter = ""  # All blobs
        elif include_public:
            visibility_filter = "AND EXISTS (SELECT 1 FROM blob_visibility bv WHERE bv.id = b.id AND bv.space = 0)"
        elif include_private:
            visibility_filter = "AND EXISTS (SELECT 1 FROM blob_visibility bv WHERE bv.id = b.id AND bv.space != 0)"
        else:
            return  # No blobs requested

        placeholders = ",".join("?" * len(blob_types))

        query = f"""
        SELECT
            b.id,
            b.data,
            b.size,
            b.codec,
            sb.type as blob_type,
            sb.ts,
            sb.author,
            sb.resource,
            r.iri
        FROM blobs b
        JOIN structural_blobs sb ON b.id = sb.id
        LEFT JOIN resources r ON sb.resource = r.id
        WHERE sb.type IN ({placeholders})
        AND b.size > 0
        AND b.data IS NOT NULL
        {visibility_filter}
        ORDER BY sb.ts DESC
        LIMIT ? OFFSET ?
        """

        params = list(blob_types) + [limit, offset]
        cursor = conn.execute(query, params)

        for row in cursor:
            try:
                decoded = self.decode_blob(row["data"], row["size"], row["codec"])
                if decoded:
                    yield {
                        "blob_id": row["id"],
                        "blob_type": row["blob_type"],
                        "timestamp": row["ts"],
                        "author_id": row["author"],
                        "resource_iri": row["iri"],
                        "decoded": decoded
                    }
            except Exception as e:
                # Skip blobs that fail to decode
                print(f"Warning: Failed to decode blob {row['id']}: {e}")

        conn.close()

    def extract_all_content(
        self,
        include_public: bool = True,
        include_private: bool = True,
        batch_size: int = 500
    ) -> Iterator[ExtractedContent]:
        """
        Extract all text content from documents and comments.

        Yields ExtractedContent objects for each text block found.
        """
        offset = 0

        while True:
            batch = list(self.get_content_blobs(
                blob_types=['Change', 'Comment'],
                include_public=include_public,
                include_private=include_private,
                limit=batch_size,
                offset=offset
            ))

            if not batch:
                break

            for blob_data in batch:
                blob_type = blob_data["blob_type"]
                decoded = blob_data["decoded"]

                try:
                    if blob_type == "Change":
                        change = DecodedChange(
                            blob_id=blob_data["blob_id"],
                            signer=decoded.get("s") or decoded.get("signer", b""),
                            timestamp=decoded.get("ts") or decoded.get("timestamp", 0),
                            genesis=decoded.get("g") or decoded.get("genesis"),
                            deps=decoded.get("d") or decoded.get("deps", []),
                            depth=decoded.get("dp") or decoded.get("depth", 0),
                            ops=decoded.get("o") or decoded.get("ops", [])
                        )
                        for content in change.extract_text():
                            content.author_id = blob_data["author_id"]
                            content.resource_iri = blob_data["resource_iri"]
                            yield content

                    elif blob_type == "Comment":
                        comment = DecodedComment(
                            blob_id=blob_data["blob_id"],
                            signer=decoded.get("s") or decoded.get("signer", b""),
                            timestamp=decoded.get("ts") or decoded.get("timestamp", 0),
                            tsid=decoded.get("tsid", ""),
                            space=decoded.get("sp") or decoded.get("space"),
                            path=decoded.get("p") or decoded.get("path", ""),
                            body=decoded.get("b") or decoded.get("body", [])
                        )
                        for content in comment.extract_text():
                            content.author_id = blob_data["author_id"]
                            content.resource_iri = blob_data["resource_iri"]
                            yield content

                except Exception as e:
                    print(f"Warning: Failed to extract from blob {blob_data['blob_id']}: {e}")

            offset += batch_size

    def get_unembedded_fts_content(
        self,
        model: str,
        content_types: List[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get FTS content that hasn't been embedded yet.

        Returns content from fts_index that doesn't have a corresponding
        entry in the embeddings table for the specified model.
        """
        if content_types is None:
            content_types = ['title', 'document', 'comment']

        conn = self._get_connection()

        placeholders = ",".join("?" * len(content_types))

        query = f"""
        SELECT
            fi.rowid,
            fi.blob_id,
            fi.block_id,
            fi.type,
            fi.version,
            fi.ts,
            f.raw_content,
            r.iri
        FROM fts_index fi
        JOIN fts f ON f.rowid = fi.rowid
        LEFT JOIN structural_blobs sb ON sb.id = fi.blob_id
        LEFT JOIN resources r ON r.id = sb.resource
        LEFT JOIN embeddings e ON e.fts_rowid = fi.rowid AND e.model = ?
        WHERE e.id IS NULL
        AND fi.type IN ({placeholders})
        AND f.raw_content != ''
        AND length(f.raw_content) > 3
        ORDER BY fi.ts DESC
        LIMIT ?
        """

        params = [model] + content_types + [limit]
        cursor = conn.execute(query, params)
        results = [dict(row) for row in cursor]
        conn.close()
        return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Decode and extract Seed content")
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("SEED_DB_PATH", DEFAULT_DB_PATH)),
                        help="Path to SQLite database")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max items to show")
    parser.add_argument("--public-only", action="store_true",
                        help="Only show public content")

    args = parser.parse_args()

    decoder = SeedBlobDecoder(args.db)

    count = 0
    for content in decoder.extract_all_content(
        include_public=True,
        include_private=not args.public_only
    ):
        print(f"[{content.content_type}] blob:{content.blob_id} block:{content.block_id}")
        print(f"  IRI: {content.resource_iri}")
        print(f"  Text: {content.text[:100]}...")
        print()

        count += 1
        if count >= args.limit:
            break

    print(f"Showed {count} content items")
