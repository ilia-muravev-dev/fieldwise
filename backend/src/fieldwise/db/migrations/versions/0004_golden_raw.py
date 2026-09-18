"""raw annotation on golden labels

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("golden_labels", sa.Column("raw", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("golden_labels", "raw")
