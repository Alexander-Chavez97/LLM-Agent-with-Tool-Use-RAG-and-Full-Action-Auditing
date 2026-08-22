-- =========================================================
-- Extensions
-- =========================================================
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gives us gen_random_uuid()

-- =========================================================
-- Sessions & Memory
-- =========================================================
-- One row per conversation. UUID (not serial) because session ids
-- are often generated client-side before any DB write happens, and
-- UUIDs avoid collisions if this ever runs as more than one process.
CREATE TABLE sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    label       TEXT  -- optional human-friendly name, e.g. "debugging pgvector question"
);

-- This table IS the agent's memory. On each turn we read all rows
-- for a session_id, ordered by created_at, and replay them as the
-- message history sent to the Claude API.
CREATE TABLE messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     JSONB NOT NULL,  -- JSONB, not TEXT: Claude's message content is a
                                  -- list of blocks (text, tool_use, tool_result),
                                  -- not a plain string. Storing it as JSONB lets us
                                  -- reconstruct the exact API payload on resume.
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_messages_session_id ON messages(session_id, created_at);

-- =========================================================
-- Action Log (auditability)
-- =========================================================
-- One row per tool invocation, success or failure. This is deliberately
-- decoupled from `messages` -- a tool call is an action the agent took,
-- not a conversational turn, and we want to be able to query
-- "show me every DB query this agent ran" without parsing message JSON.
CREATE TABLE action_log (
    id            BIGSERIAL PRIMARY KEY,
    session_id    UUID REFERENCES sessions(id) ON DELETE SET NULL,
    tool_name     TEXT NOT NULL,
    tool_input    JSONB NOT NULL,
    tool_output   JSONB,              -- NULL if the call errored before producing output
    success       BOOLEAN NOT NULL,
    error_message TEXT,               -- populated only when success = false
    latency_ms    INTEGER NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_action_log_session_id ON action_log(session_id);
CREATE INDEX idx_action_log_tool_name ON action_log(tool_name);
CREATE INDEX idx_action_log_created_at ON action_log(created_at);

-- =========================================================
-- RAG: Documents & Chunk Embeddings
-- =========================================================
CREATE TABLE documents (
    id          BIGSERIAL PRIMARY KEY,
    title       TEXT NOT NULL,
    source      TEXT,               -- e.g. "wikipedia", "manual"
    content     TEXT NOT NULL,       -- full original text, kept for reference/debugging
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- vector(384) matches sentence-transformers/all-MiniLM-L6-v2's output
-- dimension. If you swap embedding models later, this dimension MUST
-- match the new model's output size or inserts will fail.
CREATE TABLE document_chunks (
    id            BIGSERIAL PRIMARY KEY,
    document_id   BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index   INTEGER NOT NULL,   -- position of this chunk within its source doc
    chunk_text    TEXT NOT NULL,
    embedding     VECTOR(384) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- HNSW over IVFFlat: IVFFlat needs to be trained on existing data
-- (it clusters rows into `lists` buckets) and only performs well once
-- you have thousands of rows -- with ~20 docs / a couple hundred
-- chunks, that clustering would be close to meaningless. HNSW builds
-- a graph incrementally, has no minimum-data requirement, and gives
-- good recall at small-to-medium scale, at the cost of slightly
-- slower inserts and more memory -- a fine trade for this project.
CREATE INDEX idx_document_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops);
