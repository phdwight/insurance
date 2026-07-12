"""Create app + catalog schemas and enable pgvector

Revision ID: 0001
Revises:
Create Date: 2026-07-10

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute("CREATE SCHEMA IF NOT EXISTS catalog")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS catalog CASCADE")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE")
    op.execute("DROP EXTENSION IF EXISTS vector")
