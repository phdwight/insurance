"""app.llm_usage — self-hosted LLM spend ledger (token economy phase 5).

One row per (day, model, role) aggregating call count and token totals; the
agent's usage callbacks upsert into it and GET /ops/usage reads it. Cache hits
are recorded as zero-token rows so avoided spend is visible next to real spend.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-16

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE app.llm_usage (
            day            date   NOT NULL,
            model          text   NOT NULL,
            role           text   NOT NULL,
            calls          bigint NOT NULL DEFAULT 0,
            input_tokens   bigint NOT NULL DEFAULT 0,
            output_tokens  bigint NOT NULL DEFAULT 0,
            PRIMARY KEY (day, model, role)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.llm_usage")
