"""Creating documents: hashing, storing the original, rendering and storing pages."""

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldwise.db.models import Document
from fieldwise.documents.render import PDF_MIME, render_pages, sniff_mime
from fieldwise.storage import Storage

EXTENSIONS = {PDF_MIME: "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def page_key(document_id: uuid.UUID, page: int) -> str:
    return f"documents/{document_id}/pages/{page}.jpg"


def create_document(
    session: Session,
    storage: Storage,
    *,
    data: bytes,
    name: str,
    source: str,
    split: str | None = None,
    external_id: str | None = None,
) -> Document:
    """Stores the original and its rendered pages; returns the existing row for duplicate bytes."""
    sha256 = hashlib.sha256(data).hexdigest()
    existing = session.scalars(select(Document).where(Document.sha256 == sha256)).first()
    if existing is not None:
        return existing

    mime = sniff_mime(data)
    pages = render_pages(data, mime)
    document_id = uuid.uuid4()
    storage_key = f"documents/{document_id}/original.{EXTENSIONS.get(mime, 'bin')}"
    storage.put(storage_key, data, mime)
    page_records = []
    for page in pages:
        key = page_key(document_id, page.page)
        storage.put(key, page.jpeg, "image/jpeg")
        page_records.append(
            {"page": page.page, "key": key, "width": page.width, "height": page.height}
        )

    document = Document(
        id=document_id,
        name=name,
        source=source,
        split=split,
        external_id=external_id,
        mime=mime,
        sha256=sha256,
        storage_key=storage_key,
        page_count=len(pages),
        pages=page_records,
    )
    session.add(document)
    session.flush()
    return document
