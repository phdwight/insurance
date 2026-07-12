"""Query-time embeddings — thin re-export of the shared Voyage client."""

from shared.embeddings import embed_query, embeddings_enabled

__all__ = ["embed_query", "embeddings_enabled"]
