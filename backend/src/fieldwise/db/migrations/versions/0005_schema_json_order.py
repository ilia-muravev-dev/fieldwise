"""keep key order of authored schemas (json instead of jsonb)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # JSONB normalises object key order; the authored field order is meaningful (reports, UI).
    op.execute(
        "ALTER TABLE schemas ALTER COLUMN json_schema TYPE json USING json_schema::text::json"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE schemas ALTER COLUMN json_schema TYPE jsonb USING json_schema::jsonb")
