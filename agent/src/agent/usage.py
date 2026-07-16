"""LLM spend observability: a self-hosted token ledger (token economy phase 5).

Every LLM call records (day, model, role) -> calls + input/output tokens into
``app.llm_usage`` (migration 0008) via LangChain's UsageMetadataCallbackHandler.
Explanation-cache hits are recorded too (zero tokens) so avoided spend is
visible next to real spend. ``GET /ops/usage`` on this service exposes the
ledger; LangSmith remains the per-call *tracing* tool — this is the always-on
spend counter that works without any SaaS.

``DAILY_TOKEN_BUDGET`` (total tokens/day, 0 or empty = no budget) turns the
ledger into an alarm: crossing it logs a WARNING once per process per day —
wire container-log alerting to it, or flip ``LLM_ECONOMY`` to lean/deterministic
(the phase-4 ladder) until the day rolls over. Recording is best-effort and
fails safe: a broken ledger must never break a conversation.
"""

import logging
import os
from typing import Any

logger = logging.getLogger("agent")

_warned_days: set[str] = set()  # budget warning fires once per process per day


def _dsn() -> str | None:
    url = os.environ.get("DATABASE_URL")
    return url.replace("postgresql+psycopg://", "postgresql://") if url else None


def daily_token_budget() -> int:
    try:
        return int(os.environ.get("DAILY_TOKEN_BUDGET", "0") or "0")
    except ValueError:
        return 0


def tracker():
    """A per-call LangChain callback that collects usage_metadata by model."""
    from langchain_core.callbacks import UsageMetadataCallbackHandler

    return UsageMetadataCallbackHandler()


async def record(role: str, usage_by_model: dict[str, Any]) -> None:
    """Upsert one ledger row per model used by a call. Best-effort."""
    rows = [
        (
            model,
            role,
            int(usage.get("input_tokens") or 0),
            int(usage.get("output_tokens") or 0),
        )
        for model, usage in (usage_by_model or {}).items()
    ]
    if rows:
        await _write(rows)
        await _check_budget()


async def record_event(role: str, model: str = "-") -> None:
    """A zero-token ledger event (e.g. an explanation-cache hit). Best-effort."""
    await _write([(model, role, 0, 0)])


async def _write(rows: list[tuple[str, str, int, int]]) -> None:
    from agent import db

    if _dsn() is None:
        return
    try:
        async with db.connection() as conn:
            for model, role, input_tokens, output_tokens in rows:
                await conn.execute(
                    "INSERT INTO app.llm_usage (day, model, role, calls, input_tokens,"
                    " output_tokens) VALUES (current_date, %s, %s, 1, %s, %s)"
                    " ON CONFLICT (day, model, role) DO UPDATE SET"
                    " calls = app.llm_usage.calls + 1,"
                    " input_tokens = app.llm_usage.input_tokens + EXCLUDED.input_tokens,"
                    " output_tokens = app.llm_usage.output_tokens + EXCLUDED.output_tokens",
                    (model, role, input_tokens, output_tokens),
                )
    except Exception:
        logger.warning("llm usage write failed; skipping", exc_info=True)


async def _today_total() -> int | None:
    from agent import db

    if _dsn() is None:
        return None
    try:
        async with db.connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT coalesce(sum(input_tokens + output_tokens), 0) AS total"
                    " FROM app.llm_usage WHERE day = current_date"
                )
            ).fetchone()
            return int(row["total"]) if row else None
    except Exception:
        return None


async def _check_budget() -> None:
    budget = daily_token_budget()
    if budget <= 0:
        return
    total = await _today_total()
    if total is None or total <= budget:
        return
    from datetime import date

    today = date.today().isoformat()
    if today not in _warned_days:
        _warned_days.add(today)
        logger.warning(
            "DAILY_TOKEN_BUDGET exceeded: %d tokens spent today (budget %d). "
            "Consider LLM_ECONOMY=lean or deterministic until the day rolls over.",
            total,
            budget,
        )


async def summary(days: int = 7) -> dict[str, Any]:
    """Ledger for the ops endpoint: per-day rows plus today's budget status."""
    from agent import db

    if _dsn() is None:
        return {"rows": [], "budget": daily_token_budget(), "today_total": 0}
    async with db.connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT day::text AS day, model, role, calls, input_tokens, output_tokens"
                " FROM app.llm_usage WHERE day > current_date - %s"
                " ORDER BY day DESC, model, role",
                (days,),
            )
        ).fetchall()
        today_row = await (
            await conn.execute(
                "SELECT coalesce(sum(input_tokens + output_tokens), 0) AS total"
                " FROM app.llm_usage WHERE day = current_date"
            )
        ).fetchone()
    ledger = [dict(row) for row in rows]
    today_total = int(today_row["total"]) if today_row else 0
    budget = daily_token_budget()
    return {
        "rows": ledger,
        "budget": budget,
        "today_total": today_total,
        "over_budget": bool(budget) and today_total > budget,
    }
