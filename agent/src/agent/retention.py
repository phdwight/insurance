"""Session retention: Data Privacy Act minimization for checkpointed chats.

Checkpoints contain personal data (age, budget, risk notes). Sessions idle
longer than SESSION_TTL_DAYS are purged — their LangGraph checkpoint rows and
the last-seen record. Not a conversation timeout: an active user can return
any time within the TTL and resume exactly where they stopped.

Functions take an open psycopg async connection so tests can pass a fake.
"""

import asyncio
import logging
import os

logger = logging.getLogger("agent")

# LangGraph checkpointer tables, all keyed by thread_id.
CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


def session_ttl_days() -> int:
    return int(os.environ.get("SESSION_TTL_DAYS", "30"))


def retention_interval_seconds() -> int:
    return int(os.environ.get("RETENTION_INTERVAL_SECONDS", "3600"))


async def touch_session(conn, thread_id: str) -> None:
    await conn.execute(
        "INSERT INTO app.sessions (thread_id, last_seen) VALUES (%s, now()) "
        "ON CONFLICT (thread_id) DO UPDATE SET last_seen = now()",
        (thread_id,),
    )


async def purge_stale_sessions(conn, ttl_days: int) -> int:
    """Delete checkpoints + session rows for sessions idle past the TTL.
    Returns the number of purged sessions."""
    stale = await conn.execute(
        "SELECT thread_id FROM app.sessions WHERE last_seen < now() - %s * interval '1 day'",
        (ttl_days,),
    )
    # Pool connections use dict_row (see agent/db.py) — access by column name.
    thread_ids = [row["thread_id"] for row in await stale.fetchall()]
    if not thread_ids:
        return 0

    for table in CHECKPOINT_TABLES:
        await conn.execute(
            f"DELETE FROM {table} WHERE thread_id = ANY(%s)",  # noqa: S608 - fixed table names
            (thread_ids,),
        )
    await conn.execute(
        "DELETE FROM app.sessions WHERE thread_id = ANY(%s)", (thread_ids,)
    )
    return len(thread_ids)


async def retention_loop() -> None:
    """Background task: purge on an interval, forever. Failures are logged and
    retried next round — retention must never take the service down."""
    from agent import db, expl_cache

    while True:
        try:
            async with db.connection() as conn:
                purged = await purge_stale_sessions(conn, session_ttl_days())
                if purged:
                    logger.info("retention: purged %d stale session(s)", purged)
                stale = await expl_cache.purge_stale(conn, expl_cache.cache_ttl_days())
                if stale:
                    logger.info("retention: purged %d stale cached explanation(s)", stale)
        except Exception:
            logger.warning("retention pass failed; will retry", exc_info=True)
        await asyncio.sleep(retention_interval_seconds())


async def record_activity(thread_id: str) -> None:
    """Fire-and-forget last-seen upsert; never disturbs the chat request."""
    from agent import db

    try:
        async with db.connection() as conn:
            await touch_session(conn, thread_id)
    except Exception:
        logger.warning("failed to record session activity", exc_info=True)
