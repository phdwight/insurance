"""Catalog persistence for the ingestion pipeline (catalog schema tables).

Raw SQL like mcp-server's queries.py — same schema, write path only.
"""

import json
import os
import re
from typing import Any

from shared.embeddings import embed_documents, embedding_model, embeddings_enabled
from sqlalchemy import Engine, create_engine, text

_engine: Engine | None = None


class InsurerNotFound(LookupError):
    pass


class SlugConflict(ValueError):
    pass


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://insurance:insurance@localhost:5432/insurance",
        )
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def get_or_create_source_document(
    insurer_slug: str | None,
    file_hash: str,
    file_ref: str,
    doc_type: str,
    uploaded_by: str,
    parse_status: str = "parsed",
) -> tuple[str, bool]:
    """Returns (document_id, created). Re-uploading the same file reuses the
    stored document and just refreshes its parse_status — the caller then
    creates a fresh extraction run (useful when a first parse/extraction was
    poor and the reviewer wants a redo). insurer_slug is optional — the
    insurer is normally detected from the document at extraction time."""
    with get_engine().begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM catalog.source_documents WHERE file_hash = :hash"),
            {"hash": file_hash},
        ).scalar()
        if existing:
            conn.execute(
                text(
                    "UPDATE catalog.source_documents SET parse_status = :status "
                    "WHERE id = :id"
                ),
                {"status": parse_status, "id": existing},
            )
            return str(existing), False

        insurer_id = None
        if insurer_slug:
            insurer_id = conn.execute(
                text("SELECT id FROM catalog.insurers WHERE slug = :slug"),
                {"slug": insurer_slug},
            ).scalar()
            if insurer_id is None:
                raise InsurerNotFound(insurer_slug)

        return str(
            conn.execute(
                text(
                    """
                    INSERT INTO catalog.source_documents
                        (insurer_id, file_hash, file_ref, doc_type, uploaded_by,
                         parse_status)
                    VALUES (:insurer_id, :hash, :ref, :doc_type, :by, :parse_status)
                    RETURNING id
                    """
                ),
                {
                    "insurer_id": insurer_id,
                    "hash": file_hash,
                    "ref": file_ref,
                    "doc_type": doc_type,
                    "by": uploaded_by,
                    "parse_status": parse_status,
                },
            ).scalar_one()
        ), True


def create_extraction_run(
    source_document_id: str, model: str, output: dict | None, status: str
) -> str:
    with get_engine().begin() as conn:
        return str(
            conn.execute(
                text(
                    """
                    INSERT INTO catalog.extraction_runs
                        (source_document_id, model, output, status)
                    VALUES (:doc_id, :model, :output, :status)
                    RETURNING id
                    """
                ),
                {
                    "doc_id": source_document_id,
                    "model": model,
                    "output": json.dumps(output) if output is not None else None,
                    "status": status,
                },
            ).scalar_one()
        )


def finalize_extraction_run(
    run_id: str, model: str, output: dict | None, status: str
) -> None:
    """Move a run out of 'processing' to its terminal status once background
    parse + extraction finish (or fail). Never loses a result — a failure is
    recorded as status='failed' with the reason in output."""
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE catalog.extraction_runs
                SET model = :model, output = :output, status = :status
                WHERE id = :id
                """
            ),
            {
                "id": run_id,
                "model": model,
                "output": json.dumps(output) if output is not None else None,
                "status": status,
            },
        )


def update_parse_status(document_id: str, parse_status: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE catalog.source_documents SET parse_status = :status WHERE id = :id"
            ),
            {"status": parse_status, "id": document_id},
        )


def update_doc_type(document_id: str, doc_type: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE catalog.source_documents SET doc_type = :t WHERE id = :id"),
            {"t": doc_type, "id": document_id},
        )


def claim_next_run() -> dict[str, Any] | None:
    """Atomically claim one 'queued' run for a worker: flip it to 'processing'
    and stamp claimed_at. FOR UPDATE SKIP LOCKED means concurrent workers never
    grab the same row. Returns {id, source_document_id, file_ref} or None when
    the queue is empty."""
    with get_engine().begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE catalog.extraction_runs
                SET status = 'processing', claimed_at = now()
                WHERE id = (
                    SELECT id FROM catalog.extraction_runs
                    WHERE status = 'queued'
                    ORDER BY created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id, source_document_id
                """
            )
        ).first()
        if row is None:
            return None
        run = dict(row._mapping)
        run["file_ref"] = conn.execute(
            text("SELECT file_ref FROM catalog.source_documents WHERE id = :id"),
            {"id": run["source_document_id"]},
        ).scalar()
        return run


def reclaim_stale_runs(older_than_seconds: int) -> int:
    """Requeue runs a crashed worker left stuck in 'processing' past the stale
    window, so an upload is never stranded. Returns how many were requeued."""
    with get_engine().begin() as conn:
        return conn.execute(
            text(
                """
                UPDATE catalog.extraction_runs
                SET status = 'queued', claimed_at = NULL
                WHERE status = 'processing'
                  AND claimed_at < now() - make_interval(secs => :secs)
                """
            ),
            {"secs": older_than_seconds},
        ).rowcount


def list_insurers() -> list[dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT name, slug FROM catalog.insurers ORDER BY name")
        )
        return [dict(row._mapping) for row in rows]


def get_document(document_id: str) -> dict[str, Any] | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, file_ref, doc_type, parse_status
                FROM catalog.source_documents WHERE id = :id
                """
            ),
            {"id": document_id},
        ).first()
        return dict(row._mapping) if row else None


def list_reviews(status: str = "pending_review") -> list[dict[str, Any]]:
    sql = text(
        """
        SELECT r.id, r.status, r.model, r.created_at, r.output,
               d.doc_type, d.file_ref, d.parse_status,
               i.name AS insurer_name, i.slug AS insurer_slug
        FROM catalog.extraction_runs r
        JOIN catalog.source_documents d ON d.id = r.source_document_id
        LEFT JOIN catalog.insurers i ON i.id = d.insurer_id
        WHERE r.status = :status
        ORDER BY r.created_at
        """
    )
    with get_engine().connect() as conn:
        return [dict(row._mapping) for row in conn.execute(sql, {"status": status})]


def get_review(run_id: str) -> dict[str, Any] | None:
    sql = text(
        """
        SELECT r.id, r.status, r.model, r.output, r.source_document_id,
               d.insurer_id, d.file_ref, d.parse_status,
               i.slug AS insurer_slug, i.name AS insurer_name
        FROM catalog.extraction_runs r
        JOIN catalog.source_documents d ON d.id = r.source_document_id
        LEFT JOIN catalog.insurers i ON i.id = d.insurer_id
        WHERE r.id = :id
        """
    )
    with get_engine().connect() as conn:
        row = conn.execute(sql, {"id": run_id}).first()
        return dict(row._mapping) if row else None


def reject(run_id: str, reviewed_by: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE catalog.extraction_runs
                SET status = 'rejected', reviewed_by = :by, reviewed_at = now()
                WHERE id = :id
                """
            ),
            {"id": run_id, "by": reviewed_by},
        )


def _get_or_create_insurer(conn, insurer_name: str) -> Any:
    """The reviewer-confirmed insurer name is truth; unknown insurers are
    created on publish (that's how new insurers enter the catalog)."""
    insurer_slug = slugify(insurer_name)
    insurer_id = conn.execute(
        text("SELECT id FROM catalog.insurers WHERE slug = :slug"),
        {"slug": insurer_slug},
    ).scalar()
    if insurer_id is None:
        insurer_id = conn.execute(
            text(
                "INSERT INTO catalog.insurers (name, slug) VALUES (:name, :slug) "
                "RETURNING id"
            ),
            {"name": insurer_name.strip(), "slug": insurer_slug},
        ).scalar_one()
    return insurer_id


def publish(run_id: str, draft: dict[str, Any], reviewed_by: str) -> dict[str, Any]:
    """Approve a review: create published policy + version (+ embedding)."""
    review = get_review(run_id)
    if review is None:
        raise LookupError(run_id)

    slug = slugify(draft["name"])
    with get_engine().begin() as conn:
        if conn.execute(
            text("SELECT 1 FROM catalog.policies WHERE slug = :slug"), {"slug": slug}
        ).first():
            raise SlugConflict(slug)

        insurer_id = _get_or_create_insurer(conn, draft["insurer_name"])
        conn.execute(
            text("UPDATE catalog.source_documents SET insurer_id = :iid WHERE id = :doc"),
            {"iid": insurer_id, "doc": review["source_document_id"]},
        )

        policy_id = conn.execute(
            text(
                """
                INSERT INTO catalog.policies
                    (insurer_id, product_line_id, name, slug, status)
                SELECT :insurer_id, pl.id, :name, :slug, 'published'
                FROM catalog.product_lines pl WHERE pl.code = :line
                RETURNING id
                """
            ),
            {
                "insurer_id": insurer_id,
                "name": draft["name"],
                "slug": slug,
                "line": draft["product_line"],
            },
        ).scalar_one()

        version_id = conn.execute(
            text(
                """
                INSERT INTO catalog.policy_versions
                    (policy_id, version, summary, premium_min, premium_max,
                     premium_frequency, eligibility, coverage, exclusions, riders,
                     source_document_id, verified_at, published_at)
                VALUES
                    (:policy_id, 1, :summary, :premium_min, :premium_max,
                     :premium_frequency, :eligibility, :coverage, :exclusions,
                     :riders, :doc_id, now(), now())
                RETURNING id
                """
            ),
            {
                "policy_id": policy_id,
                "summary": draft["summary"],
                "premium_min": draft.get("premium_min"),
                "premium_max": draft.get("premium_max"),
                "premium_frequency": draft.get("premium_frequency"),
                "eligibility": json.dumps(draft.get("eligibility") or {}),
                "coverage": json.dumps(draft["coverage"]),
                "exclusions": json.dumps(draft.get("exclusions") or []),
                "riders": json.dumps(draft.get("riders") or []),
                "doc_id": review["source_document_id"],
            },
        ).scalar_one()

        if embeddings_enabled():
            text_used = f"{draft['name']}. {draft['summary']}"
            [embedding] = embed_documents([text_used])
            conn.execute(
                text(
                    """
                    INSERT INTO catalog.policy_embeddings
                        (policy_version_id, embedding, model, text_used)
                    VALUES (:vid, :embedding, :model, :text_used)
                    """
                ),
                {
                    "vid": version_id,
                    "embedding": str(embedding),
                    "model": embedding_model(),
                    "text_used": text_used,
                },
            )

        conn.execute(
            text(
                """
                UPDATE catalog.extraction_runs
                SET status = 'approved', reviewed_by = :by, reviewed_at = now()
                WHERE id = :id
                """
            ),
            {"id": run_id, "by": reviewed_by},
        )

    return {"policy_id": str(policy_id), "version_id": str(version_id), "slug": slug}
