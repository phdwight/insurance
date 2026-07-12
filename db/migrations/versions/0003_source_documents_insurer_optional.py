"""source_documents.insurer_id optional — insurer is detected from the
document during extraction and confirmed at review, not pre-declared.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE catalog.source_documents ALTER COLUMN insurer_id DROP NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE catalog.source_documents ALTER COLUMN insurer_id SET NOT NULL"
    )
