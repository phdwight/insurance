"""extraction_runs becomes a durable job queue for the ingestion worker.

Uploads enqueue a run as 'queued' and return immediately; a separate worker
claims runs (FOR UPDATE SKIP LOCKED), sets 'processing', and finalizes them.
claimed_at lets a startup sweep requeue runs a crashed worker abandoned, so a
restart never strands an upload. The partial index keeps the claim query cheap.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-14

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE catalog.extraction_runs ADD COLUMN claimed_at timestamptz")
    op.execute(
        "CREATE INDEX idx_extraction_runs_queued "
        "ON catalog.extraction_runs (created_at) WHERE status = 'queued'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS catalog.idx_extraction_runs_queued")
    op.execute("ALTER TABLE catalog.extraction_runs DROP COLUMN IF EXISTS claimed_at")
