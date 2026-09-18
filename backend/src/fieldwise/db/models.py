"""ORM models. Migrations live in fieldwise/db/migrations and are written by hand."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 384  # BAAI/bge-small-en-v1.5 via fastembed


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Schema(Base):
    """A versioned extraction schema: the authored JSON Schema plus per-field matcher metadata."""

    __tablename__ = "schemas"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_schemas_name_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    json_schema: Mapped[dict[str, Any]] = mapped_column(JSONB)
    field_meta: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    golden_labels: Mapped[list["GoldenLabel"]] = relationship(back_populates="schema")


class Document(Base):
    """An uploaded or imported document, its rendered pages and OCR output."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(16))  # upload | cord
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    split: Mapped[str | None] = mapped_column(String(16))  # train | validation | test
    mime: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    page_count: Mapped[int] = mapped_column(Integer)
    pages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    ocr_status: Mapped[str] = mapped_column(String(16), default="pending")
    ocr_text: Mapped[str | None] = mapped_column(Text)
    ocr_words: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    golden_labels: Mapped[list["GoldenLabel"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class GoldenLabel(Base):
    """Ground truth for a document under a schema: from the dataset, or a reviewer's correction."""

    __tablename__ = "golden_labels"
    __table_args__ = (
        UniqueConstraint("document_id", "schema_id", "source", name="uq_golden_doc_schema_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    schema_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schemas.id", ondelete="CASCADE"))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(16))  # dataset | correction
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="golden_labels")
    schema: Mapped[Schema] = relationship(back_populates="golden_labels")


class ExtractionRun(Base):
    """One model call over one document under one schema, with everything needed to audit it."""

    __tablename__ = "extraction_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    schema_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schemas.id", ondelete="CASCADE"))
    prompt_version: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(64))
    effort: Mapped[str] = mapped_column(String(8))
    fewshot_k: Mapped[int] = mapped_column(Integer, default=0)
    use_ocr_text: Mapped[bool] = mapped_column(default=True)
    provider: Mapped[str] = mapped_column(String(16))
    # queued | running | succeeded | truncated | failed
    status: Mapped[str] = mapped_column(String(16), default="queued")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidences: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    boxes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    fewshot_document_ids: Mapped[list[str] | None] = mapped_column(JSONB)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column()
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    served_model: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    repair_rounds: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    document: Mapped[Document] = relationship()
    schema: Mapped[Schema] = relationship()


class EvalRun(Base):
    """A measurement: one configuration over a labelled split, with the aggregate numbers."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schema_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schemas.id", ondelete="CASCADE"))
    prompt_version: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(64))
    effort: Mapped[str] = mapped_column(String(8))
    fewshot_k: Mapped[int] = mapped_column(Integer, default=0)
    use_ocr_text: Mapped[bool] = mapped_column(default=True)
    provider: Mapped[str] = mapped_column(String(16))
    split: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(8), default="sync")  # sync | batch
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | done | failed
    doc_count: Mapped[int] = mapped_column(Integer, default=0)
    reps: Mapped[int] = mapped_column(Integer, default=1)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    per_field: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    lists: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    overall_accuracy: Mapped[float | None] = mapped_column()
    lenient_accuracy: Mapped[float | None] = mapped_column()
    value_accuracy: Mapped[float | None] = mapped_column()
    doc_exact_rate: Mapped[float | None] = mapped_column()
    cost_usd: Mapped[float | None] = mapped_column()
    cost_per_doc: Mapped[float | None] = mapped_column()
    p50_ms: Mapped[int | None] = mapped_column(Integer)
    p95_ms: Mapped[int | None] = mapped_column(Integer)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    schema: Mapped[Schema] = relationship()
    results: Mapped[list["EvalResult"]] = relationship(
        back_populates="eval_run", cascade="all, delete-orphan"
    )


class EvalResult(Base):
    """The graded outcome of one extraction inside an eval run."""

    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eval_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE")
    )
    rep: Mapped[int] = mapped_column(Integer, default=1)
    outcomes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    eval_run: Mapped[EvalRun] = relationship(back_populates="results")
    document: Mapped[Document] = relationship()
    extraction_run: Mapped[ExtractionRun] = relationship()
