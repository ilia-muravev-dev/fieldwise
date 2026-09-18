from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from fieldwise.documents.ocr import FakeOcrProvider, OcrSpan
from fieldwise.documents.ocr_service import ocr_document, pending_documents
from fieldwise.documents.service import create_document
from fieldwise.storage import LocalStorage

pytestmark = pytest.mark.integration


def _pdf(pages: int) -> bytes:
    buffer = BytesIO()
    images = [Image.new("RGB", (200, 300), "white") for _ in range(pages)]
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def test_ocr_document_stores_text_and_spans_per_page(
    session: Session, storage: LocalStorage
) -> None:
    document = create_document(session, storage, data=_pdf(2), name="two.pdf", source="upload")
    provider = FakeOcrProvider([OcrSpan("TOTAL", (10, 10, 50, 20), 0.9)])

    ocr_document(document, storage, provider)
    session.flush()

    assert document.ocr_status == "done"
    assert provider.calls == 2
    assert document.ocr_text == "--- page 1 ---\nTOTAL\n\n--- page 2 ---\nTOTAL"
    assert document.ocr_words is not None
    assert [r["page"] for r in document.ocr_words] == [1, 2]
    assert pending_documents(session) == []
    assert [d.id for d in pending_documents(session, force=True)] == [document.id]


def test_ocr_failure_is_recorded(session: Session, storage: LocalStorage) -> None:
    document = create_document(session, storage, data=_pdf(1), name="one.pdf", source="upload")

    class Broken:
        def recognise(self, jpeg: bytes) -> list[OcrSpan]:
            raise RuntimeError("engine exploded")

    with pytest.raises(RuntimeError):
        ocr_document(document, storage, Broken())
    assert document.ocr_status == "failed"
    assert [d.id for d in pending_documents(session)] == [document.id]
