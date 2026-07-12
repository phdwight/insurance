"""Catalog tables: insurers, product lines, policies, versions, embeddings, sources

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-10

Embedding dimension is 1024 (voyage-3.5). If the embedding model changes,
add a migration that recreates catalog.policy_embeddings.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE catalog.insurers (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name            text NOT NULL UNIQUE,
            slug            text NOT NULL UNIQUE,
            website         text,
            ic_license_ref  text,
            created_at      timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.product_lines (
            id    smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code  text NOT NULL UNIQUE,
            name  text NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO catalog.product_lines (code, name) VALUES
            ('life', 'Life Insurance'),
            ('health', 'Health Insurance'),
            ('travel', 'Travel Insurance'),
            ('pet', 'Pet Insurance')
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.source_documents (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            insurer_id    uuid NOT NULL REFERENCES catalog.insurers(id),
            file_hash     text NOT NULL UNIQUE,
            file_ref      text NOT NULL,
            doc_type      text NOT NULL,
            uploaded_by   text,
            uploaded_at   timestamptz NOT NULL DEFAULT now(),
            parse_status  text NOT NULL DEFAULT 'pending'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.policies (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            insurer_id       uuid NOT NULL REFERENCES catalog.insurers(id),
            product_line_id  smallint NOT NULL REFERENCES catalog.product_lines(id),
            name             text NOT NULL,
            slug             text NOT NULL UNIQUE,
            status           text NOT NULL DEFAULT 'draft',
            created_at       timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_policies_insurer ON catalog.policies (insurer_id)")
    op.execute("CREATE INDEX idx_policies_line ON catalog.policies (product_line_id)")
    op.execute(
        """
        CREATE TABLE catalog.policy_versions (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            policy_id           uuid NOT NULL REFERENCES catalog.policies(id),
            version             integer NOT NULL,
            effective_date      date,
            verified_at         timestamptz,
            summary             text NOT NULL,
            currency            text NOT NULL DEFAULT 'PHP',
            premium_min         numeric(14, 2),
            premium_max         numeric(14, 2),
            premium_frequency   text,
            eligibility         jsonb NOT NULL DEFAULT '{}'::jsonb,
            coverage            jsonb NOT NULL,
            exclusions          jsonb NOT NULL DEFAULT '[]'::jsonb,
            riders              jsonb NOT NULL DEFAULT '[]'::jsonb,
            extras              jsonb NOT NULL DEFAULT '{}'::jsonb,
            source_url          text,
            source_document_id  uuid REFERENCES catalog.source_documents(id),
            published_at        timestamptz,
            superseded_at       timestamptz,
            UNIQUE (policy_id, version)
        )
        """
    )
    op.execute("CREATE INDEX idx_versions_policy ON catalog.policy_versions (policy_id)")
    # Fast path for "current published version" lookups
    op.execute(
        """
        CREATE UNIQUE INDEX idx_versions_current
            ON catalog.policy_versions (policy_id)
            WHERE superseded_at IS NULL AND published_at IS NOT NULL
        """
    )
    op.execute(
        f"""
        CREATE TABLE catalog.policy_embeddings (
            policy_version_id  uuid PRIMARY KEY REFERENCES catalog.policy_versions(id)
                               ON DELETE CASCADE,
            embedding          vector({EMBEDDING_DIM}) NOT NULL,
            model              text NOT NULL,
            text_used          text NOT NULL,
            created_at         timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_embeddings_hnsw
            ON catalog.policy_embeddings
            USING hnsw (embedding vector_cosine_ops)
        """
    )
    op.execute(
        """
        CREATE TABLE catalog.extraction_runs (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source_document_id  uuid NOT NULL REFERENCES catalog.source_documents(id),
            model               text NOT NULL,
            output              jsonb,
            field_confidences   jsonb,
            status              text NOT NULL DEFAULT 'pending',
            reviewed_by         text,
            reviewed_at         timestamptz,
            created_at          timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    for table in (
        "extraction_runs",
        "policy_embeddings",
        "policy_versions",
        "policies",
        "source_documents",
        "product_lines",
        "insurers",
    ):
        op.execute(f"DROP TABLE IF EXISTS catalog.{table} CASCADE")
