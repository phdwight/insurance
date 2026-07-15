"""Track auto-correction passes on an extraction run.

When a reviewer approves a draft that fails validation, the large LLM re-reads
the document visually with the error and returns a corrected draft for another
human review — capped at a few passes. correction_attempts is that counter, so
the cap survives across approve calls.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-15

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE catalog.extraction_runs "
        "ADD COLUMN correction_attempts integer NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE catalog.extraction_runs DROP COLUMN IF EXISTS correction_attempts"
    )
