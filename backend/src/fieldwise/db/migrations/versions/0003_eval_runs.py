"""eval runs and results

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column("split", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False, server_default="sync"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reps", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("truncated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("per_field", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("lists", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("overall_accuracy", sa.Float(), nullable=True),
        sa.Column("lenient_accuracy", sa.Float(), nullable=True),
        sa.Column("value_accuracy", sa.Float(), nullable=True),
        sa.Column("doc_exact_rate", sa.Float(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("cost_per_doc", sa.Float(), nullable=True),
        sa.Column("p50_ms", sa.Integer(), nullable=True),
        sa.Column("p95_ms", sa.Integer(), nullable=True),
        sa.Column("errors", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "eval_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "extraction_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("extraction_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rep", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("outcomes", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_eval_results_eval_run_id", "eval_results", ["eval_run_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_results_eval_run_id", table_name="eval_results")
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
