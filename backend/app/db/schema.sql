CREATE EXTENSION IF NOT EXISTS vector;

-- ── Users (simple multi-user login) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(64) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT now()
);

-- ── Notebooks ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notebooks (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);

-- Migration-safe: associate notebooks with a user
ALTER TABLE notebooks
    ADD COLUMN IF NOT EXISTS user_id INT REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS notebooks_user_idx
    ON notebooks(user_id);

-- ── Sessions (opaque cookie-session tokens) ───────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT now(),
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS sessions_user_idx
    ON sessions(user_id);

-- ── Documents ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id           SERIAL PRIMARY KEY,
    filename     VARCHAR(255) NOT NULL,
    total_pages  INT,
    file_size_kb INT,
    uploaded_at  TIMESTAMP DEFAULT now()
);

-- Migration-safe: add notebook_id to documents if not already present
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS notebook_id INT REFERENCES notebooks(id) ON DELETE CASCADE;

-- Migration-safe: async ingestion state for the RabbitMQ + Celery pipeline.
-- Existing rows default to 'completed' so old uploads keep working.
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'completed';
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS file_path TEXT;

-- ── Chunks ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id          SERIAL PRIMARY KEY,
    document_id INT REFERENCES documents(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    page_number INT,
    embedding   vector(384)
);

-- ── Messages (persistent chat history) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id           SERIAL PRIMARY KEY,
    notebook_id  INT REFERENCES notebooks(id) ON DELETE CASCADE,
    role         VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content      TEXT NOT NULL,
    sources_json TEXT DEFAULT '[]',
    created_at   TIMESTAMP DEFAULT now()
);

-- ── Indexes ───────────────────────────────────────────────────────────────
-- NOTE (Phase 1 fix): no approximate vector index on chunks. An ivfflat index
-- with default lists=100 on a small chunk table makes ORDER BY embedding <=>
-- ... LIMIT 5 return 0 rows (the single probed list holds none of the rows).
-- Sequential scan gives exact cosine results at this scale.
DROP INDEX IF EXISTS chunks_embedding_idx;

CREATE INDEX IF NOT EXISTS documents_notebook_idx
    ON documents(notebook_id);

CREATE INDEX IF NOT EXISTS messages_notebook_idx
    ON messages(notebook_id, created_at);

-- ── Query Cache (semantic caching) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS query_cache (
    id SERIAL PRIMARY KEY,
    notebook_id INT REFERENCES notebooks(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    question_embedding vector(384),
    answer TEXT NOT NULL,
    sources JSONB,
    document_ids INT[],
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS query_cache_embedding_idx
    ON query_cache USING ivfflat (question_embedding vector_cosine_ops);

