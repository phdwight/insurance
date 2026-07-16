"""app.explanation_cache — writer + verifier output cached per outcome bucket.

The discriminator engine quantizes users into a bounded set of outcomes; two
users with the same profile answers against the same policy versions get the
same candidate set, so the LLM explanation and judge verdicts are identical.
Keyed by a content hash (models + prompts + profile + policy content), so a
policy re-version or prompt/model change self-invalidates. Rows unused past
EXPLANATION_CACHE_TTL_DAYS are purged by the agent's retention loop.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-16

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE app.explanation_cache (
            cache_key   text PRIMARY KEY,
            payload     jsonb NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            last_used   timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_explanation_cache_last_used ON app.explanation_cache (last_used)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.explanation_cache")
