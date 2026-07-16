"""Explanation cache: pay for writer + verifier once per outcome, not per user.

The discriminator engine quantizes users into a bounded set of outcomes — the
same profile answers against the same policy versions always produce the same
candidate set, so the writer explanation and the verifier panel's verdicts are
identical too. This cache keys the *final, panel-verified* recommendations by a
content hash of everything that could change the output:

  * the writer model and judge panel (a model swap must not serve old prose),
  * the explain + judge prompts (a prompt edit invalidates),
  * the user's profile as the writer sees it,
  * the full verified policy content (content-addressed: a re-versioned policy
    changes its fields, which changes the key — no invalidation bookkeeping).

Rows live in ``app.explanation_cache`` (migration 0007) and are purged by the
retention loop when unused past ``EXPLANATION_CACHE_TTL_DAYS``. Every operation
fails safe: any DB error is logged and treated as a miss so the conversation
always proceeds — the cache can only ever save tokens, never break a chat.

``EXPLANATION_CACHE=off`` disables it; otherwise it's on whenever DATABASE_URL
is set (the in-memory dev/test mode has nothing to cache into).
"""

import hashlib
import json
import logging
import os

logger = logging.getLogger("agent")

CONNECT_TIMEOUT_SECONDS = 3  # a slow cache must not stall the chat


def _dsn() -> str | None:
    url = os.environ.get("DATABASE_URL")
    return url.replace("postgresql+psycopg://", "postgresql://") if url else None


def enabled() -> bool:
    if os.environ.get("EXPLANATION_CACHE", "auto").lower() in ("off", "false", "0", "no"):
        return False
    return _dsn() is not None


def cache_ttl_days() -> int:
    return int(os.environ.get("EXPLANATION_CACHE_TTL_DAYS", "30"))


def cache_key(profile: dict, recommendations: dict) -> str:
    """Content hash of every input that could change the explained output.

    Computed over the recommendations BEFORE reasons are attached (the verified
    facts), so a hit can skip the writer and the judge panel entirely."""
    from agent import verifier
    from agent.config import LLM_MODEL_LARGE_1
    from agent.prompts import EXPLAIN_SYSTEM, JUDGE_SYSTEM

    material = json.dumps(
        {
            "writer": LLM_MODEL_LARGE_1,
            "judges": sorted(verifier.judge_models()),
            "prompts": [EXPLAIN_SYSTEM, JUDGE_SYSTEM],
            "profile": profile,
            "recommendations": recommendations,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(material.encode()).hexdigest()


async def get(key: str) -> dict | None:
    """Cached recommendations for the key, or None. Marks the row used."""
    import psycopg

    dsn = _dsn()
    if dsn is None:
        return None
    try:
        async with await psycopg.AsyncConnection.connect(
            dsn, autocommit=True, connect_timeout=CONNECT_TIMEOUT_SECONDS
        ) as conn:
            row = await (
                await conn.execute(
                    "UPDATE app.explanation_cache SET last_used = now() "
                    "WHERE cache_key = %s RETURNING payload",
                    (key,),
                )
            ).fetchone()
            return row[0] if row else None
    except Exception:
        logger.warning("explanation cache read failed; treating as miss", exc_info=True)
        return None


async def put(key: str, recommendations: dict) -> None:
    """Store the final (panel-verified) recommendations. Best-effort."""
    import psycopg
    from psycopg.types.json import Json

    dsn = _dsn()
    if dsn is None:
        return
    try:
        async with await psycopg.AsyncConnection.connect(
            dsn, autocommit=True, connect_timeout=CONNECT_TIMEOUT_SECONDS
        ) as conn:
            await conn.execute(
                "INSERT INTO app.explanation_cache (cache_key, payload) "
                "VALUES (%s, %s) ON CONFLICT (cache_key) DO NOTHING",
                (key, Json(recommendations, dumps=lambda obj: json.dumps(obj, default=str))),
            )
    except Exception:
        logger.warning("explanation cache write failed; skipping", exc_info=True)


async def purge_stale(conn, ttl_days: int) -> int:
    """Delete rows unused past the TTL (called from the retention loop)."""
    result = await conn.execute(
        "DELETE FROM app.explanation_cache "
        "WHERE last_used < now() - %s * interval '1 day'",
        (ttl_days,),
    )
    return result.rowcount or 0
