"""
Shared embedding model.

Both ingest.py and tools/rag_retrieve.py import from here rather than
each instantiating their own SentenceTransformer. This matters more
than it looks: if ingestion and retrieval ever used two DIFFERENT
embedding models, similarity search would silently produce garbage --
two different models don't share a coordinate space, so "closeness"
between a query embedded by one model and chunks embedded by another is
meaningless, and nothing would ever raise an error to tell you that.
Having exactly one place that defines the model makes that class of bug
structurally impossible rather than something to remember to avoid.
"""

from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # must match `vector(384)` in db/schema.sql

_model = SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]):
    """
    Embed a list of strings. normalize_embeddings=True makes each vector
    unit length, which is what pairs correctly with the cosine-distance
    operator (<=>) and the vector_cosine_ops HNSW index built in
    db/schema.sql -- cosine similarity is only meaningful on normalized
    vectors.
    """
    return _model.encode(texts, normalize_embeddings=True)


def embed_one(text: str):
    return embed([text])[0]