"""schemas, documents and golden labels

Revision ID: 0001
Revises:
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "schemas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("json_schema", postgresql.JSONB(), nullable=False),
        sa.Column("field_meta", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("name", "version", name="uq_schemas_name_version"),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=True, unique=True),
        sa.Column("split", sa.String(16), nullable=True),
        sa.Column("mime", sa.String(64), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("pages", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("ocr_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("ocr_words", postgresql.JSONB(), nullable=True),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_documents_split", "documents", ["split"])

    op.create_table(
        "golden_labels",
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
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "document_id", "schema_id", "source", name="uq_golden_doc_schema_source"
        ),
    )
    op.create_index("ix_golden_labels_document_id", "golden_labels", ["document_id"])


def downgrade() -> None:
    op.drop_table("golden_labels")
    op.drop_index("ix_documents_split", table_name="documents")
    op.drop_table("documents")
    op.drop_table("schemas")
