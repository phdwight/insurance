"""Shared async Postgres pool for the agent service (scaling slab).

One pool serves the LangGraph checkpointer, the explanation cache, the usage
ledger, and retention — instead of a single shared connection (which serializes
every concurrent conversation's checkpoint I/O) plus a fresh connection per
cache/ledger operation. Sized by ``AGENT_DB_POOL_SIZE`` (default 10; Postgres
default max_connections is 100 — budget across replicas when scaling out).

Connections carry ``dict_row`` (the checkpointer requires it — access rows by
column name, never position), ``autocommit`` and ``prepare_threshold=0`` (safe
behind transaction poolers like pgbouncer).

``connection()`` is the module seam every DB helper uses: it hands out a pooled
connection when the pool is open, else falls back to a one-off direct connect
(dev/tests without the service lifespan). Callers own their error handling —
best-effort features (cache, ledger) must keep failing safe.
"""

import os
from contextlib import asynccontextmanager

_pool = None

CONNECT_TIMEOUT_SECONDS = 3


def _dsn() -> str | None:
    url = os.environ.get("DATABASE_URL")
    return url.replace("postgresql+psycopg://", "postgresql://") if url else None


def pool_size() -> int:
    try:
        return max(2, int(os.environ.get("AGENT_DB_POOL_SIZE", "10")))
    except ValueError:
        return 10


async def open_pool(dsn: str):
    """Open the shared pool (service lifespan). Returns it for the checkpointer."""
    global _pool
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    _pool = AsyncConnectionPool(
        dsn,
        min_size=1,
        max_size=pool_size(),
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await _pool.open(wait=True, timeout=30)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def connection():
    """A pooled connection, or a one-off direct connect outside the lifespan.
    Raises when no DATABASE_URL is configured — callers that can run without a
    database must guard first (as expl_cache/usage do)."""
    if _pool is not None:
        async with _pool.connection() as conn:
            yield conn
        return

    import psycopg
    from psycopg.rows import dict_row

    dsn = _dsn()
    if dsn is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with await psycopg.AsyncConnection.connect(
        dsn,
        autocommit=True,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        row_factory=dict_row,
    ) as conn:
        yield conn
