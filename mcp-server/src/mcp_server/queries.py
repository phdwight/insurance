"""Catalog queries backing the MCP tools.

All queries read only published, non-superseded policy versions.
Results are plain dicts so tool outputs serialize directly.
"""

import logging
from typing import Any

from sqlalchemy import text

from mcp_server.db import get_engine
from mcp_server.embeddings import embed_query, embeddings_enabled

logger = logging.getLogger("mcp-server")

CURRENT_VERSIONS = """
    SELECT p.id AS policy_id, p.slug, p.name, p.status,
           i.name AS insurer_name, i.website AS insurer_website,
           pl.code AS product_line,
           v.id AS version_id, v.version, v.summary, v.currency,
           v.premium_min, v.premium_max, v.premium_frequency,
           v.eligibility, v.coverage, v.exclusions, v.riders,
           v.effective_date, v.verified_at, v.source_url
    FROM catalog.policies p
    JOIN catalog.insurers i ON i.id = p.insurer_id
    JOIN catalog.product_lines pl ON pl.id = p.product_line_id
    JOIN catalog.policy_versions v ON v.policy_id = p.id
    WHERE v.superseded_at IS NULL
      AND v.published_at IS NOT NULL
      AND p.status = 'published'
"""


def _rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in rows]


def list_product_lines() -> list[dict[str, Any]]:
    sql = text(
        """
        SELECT pl.code, pl.name, count(p.id) AS policy_count
        FROM catalog.product_lines pl
        LEFT JOIN catalog.policies p
            ON p.product_line_id = pl.id AND p.status = 'published'
        GROUP BY pl.code, pl.name
        ORDER BY pl.code
        """
    )
    with get_engine().connect() as conn:
        return _rows_to_dicts(conn.execute(sql))


def list_insurers(product_line: str | None = None) -> list[dict[str, Any]]:
    where = ""
    params: dict[str, Any] = {}
    if product_line:
        where = """
            AND EXISTS (
                SELECT 1 FROM catalog.policies p
                JOIN catalog.product_lines pl ON pl.id = p.product_line_id
                WHERE p.insurer_id = i.id AND pl.code = :line AND p.status = 'published'
            )
        """
        params["line"] = product_line
    sql = text(
        f"""
        SELECT i.name, i.slug, i.website, i.ic_license_ref
        FROM catalog.insurers i
        WHERE true {where}
        ORDER BY i.name
        """
    )
    with get_engine().connect() as conn:
        return _rows_to_dicts(conn.execute(sql, params))


def search_policies(
    product_line: str,
    needs_description: str | None = None,
    max_premium: float | None = None,
    premium_frequency: str | None = None,
    age: int | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    filters = ["pl.code = :line"]
    params: dict[str, Any] = {"line": product_line, "limit": min(limit, 20)}

    if max_premium is not None:
        filters.append("(v.premium_min IS NULL OR v.premium_min <= :max_premium)")
        params["max_premium"] = max_premium
    if premium_frequency:
        filters.append("(v.premium_frequency IS NULL OR v.premium_frequency = :freq)")
        params["freq"] = premium_frequency
    if age is not None:
        filters.append(
            """
            (COALESCE((v.eligibility->>'age_min')::int, 0) <= :age
             AND COALESCE((v.eligibility->>'age_max')::int, 200) >= :age)
            """
        )
        params["age"] = age

    where = " AND ".join(filters)
    semantic = embeddings_enabled() and bool(needs_description)
    ranking_note = None

    if semantic:
        # Embedding failures (rate limits, outages) must degrade to SQL
        # ranking, never fail the search — and never silently (note field).
        try:
            params["qvec"] = str(embed_query(needs_description))
        except Exception as error:
            logger.warning("query embedding failed; using SQL ranking", exc_info=True)
            semantic = False
            ranking_note = f"semantic ranking unavailable ({type(error).__name__})"

    if semantic:
        sql = text(
            f"""
            {CURRENT_VERSIONS} AND {where}
            AND EXISTS (SELECT 1 FROM catalog.policy_embeddings e
                        WHERE e.policy_version_id = v.id)
            ORDER BY (
                SELECT e.embedding <=> CAST(:qvec AS vector)
                FROM catalog.policy_embeddings e
                WHERE e.policy_version_id = v.id
            )
            LIMIT :limit
            """
        )
    else:
        sql = text(
            f"""
            {CURRENT_VERSIONS} AND {where}
            ORDER BY v.premium_min ASC NULLS LAST, p.name
            LIMIT :limit
            """
        )

    with get_engine().connect() as conn:
        results = _rows_to_dicts(conn.execute(sql, params))
    return {
        "ranking": "semantic" if semantic else "premium_asc",
        "ranking_note": ranking_note,
        "count": len(results),
        "results": results,
    }


def get_policy(slug: str) -> dict[str, Any] | None:
    sql = text(f"{CURRENT_VERSIONS} AND p.slug = :slug")
    with get_engine().connect() as conn:
        rows = _rows_to_dicts(conn.execute(sql, {"slug": slug}))
    return rows[0] if rows else None


COMPARE_FIELDS = [
    "name",
    "insurer_name",
    "summary",
    "currency",
    "premium_min",
    "premium_max",
    "premium_frequency",
    "eligibility",
    "coverage",
    "exclusions",
    "riders",
    "verified_at",
    "source_url",
]


def compare_policies(slugs: list[str]) -> dict[str, Any]:
    policies = [p for slug in slugs if (p := get_policy(slug))]
    matrix = {
        field: {p["slug"]: p.get(field) for p in policies} for field in COMPARE_FIELDS
    }
    return {
        "policies": [p["slug"] for p in policies],
        "not_found": [s for s in slugs if s not in {p["slug"] for p in policies}],
        "comparison": matrix,
    }
