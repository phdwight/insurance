"""Voyage AI embeddings — single client for all services.

Used by: mcp-server (query-time), db/seed.py and ingestion (document-time).
Optional everywhere: without VOYAGE_API_KEY, callers fall back to SQL ranking
or skip embedding generation.
"""

import os

import httpx

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"


def embedding_model() -> str:
    return os.environ.get("EMBEDDING_MODEL", "voyage-3.5")


def embedding_dim() -> int:
    return int(os.environ.get("EMBEDDING_DIM", "1024"))


def embeddings_enabled() -> bool:
    return bool(os.environ.get("VOYAGE_API_KEY"))


def _embed(texts: list[str], input_type: str, timeout: int) -> list[list[float]]:
    response = httpx.post(
        VOYAGE_URL,
        headers={"Authorization": f"Bearer {os.environ['VOYAGE_API_KEY']}"},
        json={
            "model": embedding_model(),
            "input": texts,
            "input_type": input_type,
            "output_dimension": embedding_dim(),
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["data"]]


def embed_query(text: str) -> list[float]:
    return _embed([text], "query", timeout=15)[0]


def embed_documents(texts: list[str]) -> list[list[float]]:
    return _embed(texts, "document", timeout=60)
