"""
RAG ingestion script. Run once (or whenever rag/documents/ changes):

    python -m rag.ingest

Reads every .txt file in rag/documents/, splits it into overlapping
chunks, embeds each chunk locally, and writes both the parent document
and its chunks into Postgres.
"""

from pathlib import Path

from pgvector.psycopg import register_vector

from db.connection import get_connection
from rag.embeddings import embed

_DOCS_DIR = Path(__file__).parent / "documents"
_CHUNK_SIZE_WORDS = 150
_CHUNK_OVERLAP_WORDS = 30


def chunk_text(text: str, chunk_size: int = _CHUNK_SIZE_WORDS, overlap: int = _CHUNK_OVERLAP_WORDS) -> list[str]:
    """
    Fixed-size sliding-window chunking with overlap.

    Splits `text` into word-count-based chunks of `chunk_size` words,
    where each new chunk starts `overlap` words before the previous one
    ended. The overlap exists because a chunk boundary falling in the
    middle of an idea would otherwise split that idea across two
    chunks, weakening both chunks' embeddings -- the same sentence
    reappearing at the start of the next chunk means the idea is still
    captured whole in at least one chunk.

    This chunks by word count rather than by token count (e.g. via
    tiktoken). Word count is simpler to reason about and close enough
    at this scale; production systems typically chunk by token count
    since that's what the embedding model actually consumes, and word
    count is only an approximation of token count.
    """
    words = text.split()
    if len(words) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap
    return chunks


def ingest():
    doc_files = sorted(_DOCS_DIR.glob("*.txt"))
    if not doc_files:
        print(f"No .txt files found in {_DOCS_DIR}")
        return

    with get_connection() as conn:
        register_vector(conn)  # teaches psycopg how to send Python
                                # lists/arrays as the Postgres `vector` type

        with conn.cursor() as cur:
            for doc_path in doc_files:
                title = doc_path.stem.replace("_", " ").title()
                content = doc_path.read_text(encoding="utf-8").strip()

                cur.execute(
                    "INSERT INTO documents (title, source, content) VALUES (%s, %s, %s) RETURNING id",
                    (title, "reference", content),
                )
                document_id = cur.fetchone()[0]

                chunks = chunk_text(content)
                embeddings = embed(chunks)

                for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                    cur.execute(
                        """
                        INSERT INTO document_chunks
                            (document_id, chunk_index, chunk_text, embedding)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (document_id, idx, chunk, embedding),
                    )

                print(f"Ingested '{title}': {len(chunks)} chunk(s)")

        conn.commit()

    print("Ingestion complete.")


if __name__ == "__main__":
    ingest()