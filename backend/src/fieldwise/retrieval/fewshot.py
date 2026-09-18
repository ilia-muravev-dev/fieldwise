"""Few-shot examples for a document: the most similar *labelled, non-test* documents by OCR-text
embedding, with their golden output. The test split is excluded in the query itself, so an eval
can never be contaminated by its own answers (ADR 0004)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from fieldwise.db.models import Document, GoldenLabel, Schema
from fieldwise.extraction.builder import FewShotExample
from fieldwise.retrieval.embeddings import Embedder

HELD_OUT_SPLITS = ("test",)
Retriever = Callable[[Document, int], list[FewShotExample]]


def embed_documents(
    session: Session,
    embedder: Embedder,
    *,
    split: str | None = None,
    limit: int | None = None,
    force: bool = False,
    batch_size: int = 32,
) -> int:
    """Fills `documents.embedding` from the OCR text; returns how many were embedded."""
    stmt = select(Document).where(Document.ocr_status == "done").order_by(Document.created_at)
    if not force:
        stmt = stmt.where(Document.embedding.is_(None))
    if split:
        stmt = stmt.where(Document.split == split)
    if limit:
        stmt = stmt.limit(limit)
    documents = [d for d in session.scalars(stmt).all() if (d.ocr_text or "").strip()]
    for start in range(0, len(documents), batch_size):
        chunk = documents[start : start + batch_size]
        vectors = embedder.embed([d.ocr_text or "" for d in chunk])
        for document, vector in zip(chunk, vectors, strict=True):
            document.embedding = vector
        session.flush()
    return len(documents)


def retrieve_examples(
    session: Session,
    document: Document,
    schema: Schema,
    k: int,
    *,
    embedder: Embedder | None = None,
) -> list[FewShotExample]:
    """The k nearest labelled documents outside the held-out splits, as prompt examples."""
    if k <= 0:
        return []
    query = document.embedding
    if query is None:
        if embedder is None or not (document.ocr_text or "").strip():
            return []
        query = embedder.embed([document.ocr_text or ""])[0]
    candidates = (
        select(Document, GoldenLabel)
        .join(GoldenLabel, GoldenLabel.document_id == Document.id)
        .where(
            GoldenLabel.schema_id == schema.id,
            Document.id != document.id,
            Document.embedding.is_not(None),
            or_(Document.split.is_(None), Document.split.not_in(HELD_OUT_SPLITS)),
        )
        .order_by(Document.embedding.cosine_distance(query), GoldenLabel.source)
        .limit(k * 3)  # a document may carry a dataset label and a correction
    )
    examples: list[FewShotExample] = []
    seen: set[object] = set()
    for candidate, label in session.execute(candidates):
        if candidate.id in seen:
            continue
        seen.add(candidate.id)
        examples.append(
            FewShotExample(
                document_id=str(candidate.external_id or candidate.id),
                ocr_text=candidate.ocr_text or "",
                output=label.data,
            )
        )
        if len(examples) == k:
            break
    return examples


def make_retriever(session: Session, schema: Schema, embedder: Embedder | None = None) -> Retriever:
    def retriever(document: Document, k: int) -> list[FewShotExample]:
        return retrieve_examples(session, document, schema, k, embedder=embedder)

    return retriever
