"""
rag_retrieve tool.

Embeds the incoming query with the SAME model used during ingestion
(rag/embeddings.py guarantees this), then finds the nearest chunks in
Postgres using pgvector's cosine-distance operator `<=>`, which is
backed by the HNSW index built in db/schema.sql. Returns each chunk's
text plus which source document it came from, so the model can
attribute its answer.
"""

from pgvector.psycopg import register_vector

from db.connection import get_connection
from rag.embeddings import embed_one

_TOP_K = 3


def run(query: str) -> dict:
    query_embedding = embed_one(query)

    with get_connection() as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            # <=> is cosine DISTANCE (0 = identical, 2 = opposite), not
            # similarity -- ORDER BY ... ASC gets the closest matches
            # first. We convert to a similarity score below since
            # "distance ascending" is confusing to read in tool output.
            cur.execute(
                """
                SELECT d.title, c.chunk_text, c.embedding <=> %s AS distance
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                ORDER BY distance ASC
                LIMIT %s
                """,
                (query_embedding, _TOP_K),
            )
            rows = cur.fetchall()

    results = [
        {
            "source_document": title,
            "text": chunk_text,
            "similarity": round(1 - distance, 4),  # cosine similarity = 1 - cosine distance
        }
        for title, chunk_text, distance in rows
    ]
    return {"results": results}


SCHEMA = {
    "name": "rag_retrieve",
    "description": (
        "Search a reference library of computer science and algorithms "
        "articles (binary search, hash tables, B-trees, graph algorithms, "
        "distributed systems concepts, etc.) for content relevant to a "
        "question. Use this for conceptual CS/algorithms questions so "
        "your answer is grounded in the reference material rather than "
        "general knowledge."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The question or topic to search the reference library for.",
            }
        },
        "required": ["query"],
    },
}