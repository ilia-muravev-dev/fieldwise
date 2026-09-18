"""Runs OCR over a document's stored pages and records the result on the row."""

from collections.abc import Sequence

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldwise.db.models import Document
from fieldwise.documents.ocr import OcrProvider, serialise_spans, spans_to_text
from fieldwise.storage import Storage

log = structlog.get_logger(__name__)


def ocr_document(document: Document, storage: Storage, provider: OcrProvider) -> Document:
    texts: list[str] = []
    records = []
    try:
        for page in document.pages:
            spans = provider.recognise(storage.get(str(page["key"])))
            records.extend(serialise_spans(spans, page=int(page["page"])))
            page_text = spans_to_text(spans)
            texts.append(
                f"--- page {page['page']} ---\n{page_text}"
                if len(document.pages) > 1
                else page_text
            )
    except Exception as error:
        document.ocr_status = "failed"
        log.warning("ocr.failed", document_id=str(document.id), error=str(error))
        raise
    document.ocr_words = records
    document.ocr_text = "\n\n".join(texts)
    document.ocr_status = "done"
    return document


def pending_documents(
    session: Session, split: str | None = None, limit: int | None = None, force: bool = False
) -> Sequence[Document]:
    stmt = select(Document).order_by(Document.created_at)
    if not force:
        stmt = stmt.where(Document.ocr_status != "done")
    if split:
        stmt = stmt.where(Document.split == split)
    if limit:
        stmt = stmt.limit(limit)
    return session.scalars(stmt).all()
