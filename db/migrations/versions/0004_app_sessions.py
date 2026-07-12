"""app.sessions — last-seen tracking for conversation retention (DPA
minimization: checkpoints hold age/budget/risk notes and must not live
forever). The purge job deletes checkpoints of sessions idle past the TTL.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE app.sessions (
            thread_id  text PRIMARY KEY,
            last_seen  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_sessions_last_seen ON app.sessions (last_seen)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.sessions")
