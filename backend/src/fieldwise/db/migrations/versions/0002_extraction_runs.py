"""extraction runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "extraction_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schema_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("schemas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prompt_version", sa.String(16), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("effort", sa.String(8), nullable=False),
        sa.Column("fewshot_k", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("use_ocr_text", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("confidences", postgresql.JSONB(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
        sa.Column("boxes", postgresql.JSONB(), nullable=True),
        sa.Column("fewshot_document_ids", postgresql.JSONB(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("served_model", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("repair_rounds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_extraction_runs_document_id", "extraction_runs", ["document_id"])
    op.create_index(
        "ix_extraction_runs_lookup",
        "extraction_runs",
        ["schema_id", "prompt_version", "model", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_runs_lookup", table_name="extraction_runs")
    op.drop_index("ix_extraction_runs_document_id", table_name="extraction_runs")
    op.drop_table("extraction_runs")
