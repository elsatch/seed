-- Embeddings table for semantic search
-- Stores vector embeddings for FTS-indexed content

CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY,
    -- Reference to the FTS index entry
    fts_rowid INTEGER NOT NULL,
    -- Blob ID for direct reference
    blob_id INTEGER NOT NULL,
    -- Block ID within document (for document content)
    block_id TEXT NOT NULL DEFAULT '',
    -- Content type: 'title', 'document', 'comment'
    content_type TEXT NOT NULL,
    -- SHA256 hash of embedded text (for dedup/cache)
    content_hash BLOB NOT NULL,
    -- Vector embedding (float32 array as blob)
    embedding BLOB NOT NULL,
    -- Embedding model identifier
    model TEXT NOT NULL,
    -- Embedding dimensions (for validation)
    dimensions INTEGER NOT NULL,
    -- Creation timestamp
    created_at INTEGER DEFAULT (strftime('%s', 'now')) NOT NULL
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_embeddings_content_hash ON embeddings (content_hash, model);
CREATE INDEX IF NOT EXISTS idx_embeddings_blob ON embeddings (blob_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_fts ON embeddings (fts_rowid);
CREATE INDEX IF NOT EXISTS idx_embeddings_type ON embeddings (content_type);

-- sqlite-vec virtual table for vector similarity search
-- Using vec0 (sqlite-vec) - successor to sqlite-vss
-- Dimensions are dynamic based on the embedding model used
-- This table is created separately when sqlite-vec is loaded
-- See: https://alexgarcia.xyz/sqlite-vec/
