"""Response and request models: the contract the web client is generated from."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FieldMetaOut(BaseModel):
    path: str
    type: str
    matcher: str
    description: str = ""
    children: list[str] = Field(default_factory=list)


class SchemaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: int
    json_schema: dict[str, Any]
    fields: list[FieldMetaOut]
    created_at: datetime


class PageOut(BaseModel):
    page: int
    width: int
    height: int
    url: str


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    prompt_version: str
    model: str
    effort: str
    fewshot_k: int
    use_ocr_text: bool
    provider: str
    cost_usd: float | None = None
    latency_ms: int | None = None
    error: str | None = None
    created_at: datetime


class DocumentOut(BaseModel):
    id: uuid.UUID
    name: str
    source: str
    split: str | None
    mime: str
    page_count: int
    ocr_status: str
    has_golden: bool
    latest_run: RunSummary | None = None
    created_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int


class OcrWordOut(BaseModel):
    text: str
    box: list[int]
    conf: float


class OcrSpanOut(BaseModel):
    page: int
    text: str
    box: list[int]
    conf: float
    words: list[OcrWordOut] = Field(default_factory=list)


class GoldenOut(BaseModel):
    source: str
    data: dict[str, Any]
    created_at: datetime


class DocumentDetail(DocumentOut):
    pages: list[PageOut]
    ocr_text: str | None
    golden: GoldenOut | None = None
    runs: list[RunSummary]


class RunOut(RunSummary):
    document_id: uuid.UUID
    schema_id: uuid.UUID
    result: dict[str, Any] | None = None
    confidences: dict[str, float] | None = None
    evidence: dict[str, Any] | None = None
    boxes: dict[str, list[list[int]]] | None = None
    fewshot_document_ids: list[str] | None = None
    input_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    output_tokens: int | None = None
    served_model: str | None = None
    request_id: str | None = None
    repair_rounds: int = 0


class ExtractRequest(BaseModel):
    schema_name: str = "receipt"
    prompt: str = "v1"
    model: str | None = None
    effort: str | None = None
    fewshot_k: int | None = None
    use_ocr_text: bool | None = None


class GoldenIn(BaseModel):
    data: dict[str, Any]


class PromptOut(BaseModel):
    name: str
    notes: str
    use_ocr_text: bool
    fewshot_k: int
    use_evidence: bool
    consistency_check: bool


class ModelOut(BaseModel):
    id: str
    provider: str
    input_per_mtok: float | None = None
    output_per_mtok: float | None = None


class EvalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    schema_id: uuid.UUID
    prompt_version: str
    model: str
    effort: str
    fewshot_k: int
    use_ocr_text: bool
    provider: str
    split: str
    mode: str
    notes: str
    status: str
    doc_count: int
    reps: int
    succeeded: int
    truncated: int
    failed: int
    per_field: dict[str, Any]
    lists: dict[str, Any]
    field_order: list[str] = Field(default_factory=list)
    overall_accuracy: float | None = None
    lenient_accuracy: float | None = None
    value_accuracy: float | None = None
    doc_exact_rate: float | None = None
    cost_usd: float | None = None
    cost_per_doc: float | None = None
    p50_ms: int | None = None
    p95_ms: int | None = None
    errors: list[dict[str, Any]]
    created_at: datetime
    finished_at: datetime | None = None


class EvalResultOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    extraction_run_id: uuid.UUID
    rep: int
    status: str
    all_correct: bool | None = None
    outcomes: dict[str, Any] | None = None


class EvalRequest(BaseModel):
    schema_name: str = "receipt"
    prompt: str = "v1"
    model: str | None = None
    effort: str | None = None
    fewshot_k: int | None = None
    use_ocr_text: bool | None = None
    split: str = "test"
    limit: int | None = None
    reps: int = 1
    mode: str = "sync"
    notes: str = ""


class TaskAccepted(BaseModel):
    task_id: str
    status: str = "queued"
