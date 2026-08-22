# LLM Agent with Tool Use, RAG, and Full Action Auditing

A small but complete LLM agent built from scratch: function calling against a live API, three real tools (calculator, Postgres query, RAG retrieval), retrieval-augmented generation over pgvector, persistent per-session memory, and full action logging for every tool call the agent makes.

Built as a portfolio project to demonstrate practical agent-engineering skills: tool orchestration, provider-agnostic design, defense-in-depth database security, and auditable AI system behavior — not just "call an LLM API."

## Architecture

```
User input
   │
   ▼
Agent loop (agent.py)
   │
   ├─► Gemini API call (function-calling enabled)
   │        │
   │        ▼
   │   Model decides: answer directly, or request a tool call
   │
   ├─► If a function_call is returned:
   │        ├─ dispatch to the matching tool (tools/)
   │        ├─ time it, log it (success or failure) to action_log
   │        └─ send the result back to the model, loop again
   │
   └─► Final text response → shown to user, full turn saved to Postgres
```

**Database does double duty**: one Postgres instance (with the pgvector extension) serves as both the app's operational store (sessions, messages, audit log) and the vector store for RAG — no separate vector DB service to run or manage.

## Features

- **Function calling** via the Gemini API (`google-genai`), with a provider-agnostic tool registry — tools are plain Python modules (`run()` + JSON-schema `SCHEMA`) with no knowledge of which LLM provider is calling them.
- **Three real tools:**
  - `calculator` — arithmetic via a whitelisted AST walker (no `eval()`), so it can't execute arbitrary code even if the input were adversarial.
  - `db_query` — lets the model write real SQL `SELECT` statements against a seeded `products` table, protected by three independent layers: app-level SELECT-only validation, automatic row-limit wrapping, and a dedicated **read-only Postgres role** with no write grants at all (so even a bug in the Python validation can't result in a write).
  - `rag_retrieve` — semantic search over a 15-document CS/algorithms reference corpus.
- **RAG with pgvector**: 15 original reference documents on CS/algorithms topics, split into ~150-word chunks with 30-word overlap (a real sliding-window chunking strategy, not one-chunk-per-doc), embedded locally with `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim, no external embedding API needed), indexed with **HNSW** (chosen over IVFFlat specifically because IVFFlat's clustering step needs a large, representative dataset to train meaningful buckets — HNSW has no such minimum and performs well at small scale).
- **Persistent per-session memory**: conversation history survives closing and reopening the process. Sessions can be explicitly resumed by ID; full message history (including intermediate tool calls) round-trips through a JSONB column in Postgres.
- **Full action logging**: every tool call — success or failure, mechanical exception or a tool-reported logical error — is logged to `action_log` with the exact input, exact output, latency in milliseconds, and a timestamp, via a single wrapper around tool dispatch rather than per-tool logging code.

## Tech stack

- **LLM**: Google Gemini API (`gemini-3.5-flash`) via `google-genai` — chosen for its free tier with full function-calling support
- **Database**: PostgreSQL 16 + pgvector, run via Docker Compose
- **Embeddings**: `sentence-transformers` (`all-MiniLM-L6-v2`), run locally — zero cost, zero external dependency
- **Driver**: `psycopg` 3

## Project structure

```
agent/
├── main.py              # CLI entry point, session resume
├── agent.py             # core tool-use loop + dispatch/logging wrapper
├── logging_utils.py      # action_log writer
├── tools/
│   ├── __init__.py        # tool registry
│   ├── calculator.py
│   ├── db_query.py
│   └── rag_retrieve.py
├── rag/
│   ├── embeddings.py       # shared embedding model (ingest + retrieval both import this)
│   ├── ingest.py           # chunking + embedding pipeline
│   └── documents/          # 15 source .txt files
├── memory/
│   └── session.py          # Content/Part <-> JSONB serialization, role translation
├── db/
│   ├── connection.py
│   ├── schema.sql
│   ├── seed.sql
│   └── roles.sql
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Setup

```bash
# 1. Start Postgres (with pgvector)
docker compose up -d

# 2. Python environment
python -m venv venv
.\venv\Scripts\Activate.ps1      # Windows
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# fill in GEMINI_API_KEY (free, from aistudio.google.com)

# 4. Ingest the RAG document set (one-time)
python -m rag.ingest

# 5. Run
python main.py
```

## Key engineering decisions

- **Read-only DB role over app-level checks alone**: the `db_query` tool authenticates as `agent_readonly`, a Postgres role with only `SELECT` granted. This means the actual safety boundary is enforced by the database itself, not just by Python string-checking — verified by directly attempting a `DELETE` as that role and confirming Postgres rejects it with a permission error.
- **HNSW over IVFFlat**: IVFFlat's index is built by clustering existing vectors into buckets, which needs a large, representative sample to produce meaningful clusters. At this project's scale (dozens of chunks), that clustering is close to meaningless. HNSW builds a navigable graph incrementally with no minimum-data requirement, so it performs well from the very first inserted vector.
- **Single dispatch-and-log wrapper, not per-tool logging**: `action_log` writes happen in exactly one place in `agent.py`, wrapping every tool call. Adding a new tool later requires zero new logging code — verified when `rag_retrieve` was added last and showed up in `action_log` automatically.
- **Provider-agnostic tool schemas**: tool definitions are plain JSON Schema; a small adapter converts them to Gemini's expected format (uppercase type names). The `tools/` directory itself has no reference to which LLM provider is in use.
- **Schema-first role translation for memory**: the `messages` table's role column deliberately uses generic `user`/`assistant` values rather than Gemini's `user`/`model` vocabulary, with translation happening only in `memory/session.py`. This keeps the database schema reusable if the project were ever pointed at a different provider.

## Known limitations

- The RAG corpus is intentionally small (15 documents) for a portfolio-scale demo; the chunking and indexing approach is designed to generalize to a much larger corpus without changes.
- `db_query` only exposes the `products` table's schema to the model via the tool description (hardcoded), rather than dynamic schema introspection — a natural next extension.
- Running on Gemini's free tier means prompts may be used to improve Google's models; not a concern for this project's synthetic data, but a real trade-off worth knowing about for anything sensitive.
