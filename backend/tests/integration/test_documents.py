from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldwise.db.models import Document, GoldenLabel
from fieldwise.documents.cord_import import CordRow, import_rows, remap_labels
from fieldwise.documents.service import create_document
from fieldwise.schemas.registry import get_schema, load_builtin, sync_builtins, upsert_schema
from fieldwise.storage import LocalStorage

pytestmark = pytest.mark.integration


def _jpeg(seed: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (120 + seed, 200), (seed * 20 % 255, 100, 100)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_sync_builtins_is_idempotent_and_versions_on_change(session: Session) -> None:
    first = sync_builtins(session)
    again = sync_builtins(session)
    assert [s.version for s in first] == [1]
    assert [s.id for s in again] == [s.id for s in first]

    changed = load_builtin("receipt")
    changed["properties"]["total"]["description"] = "changed"
    bumped = upsert_schema(session, changed)
    assert bumped.version == 2
    assert get_schema(session, "receipt").version == 2  # type: ignore[union-attr]
    assert get_schema(session, "receipt", version=1) is not None


def test_create_document_stores_original_and_pages(session: Session, storage: LocalStorage) -> None:
    document = create_document(session, storage, data=_jpeg(1), name="receipt.jpg", source="upload")
    assert document.mime == "image/jpeg"
    assert document.page_count == 1
    assert storage.exists(document.storage_key)
    assert storage.exists(document.pages[0]["key"])
    assert document.pages[0]["width"] == 121

    duplicate = create_document(session, storage, data=_jpeg(1), name="again.jpg", source="upload")
    assert duplicate.id == document.id


def test_import_rows_creates_documents_with_golden_labels(
    session: Session, storage: LocalStorage
) -> None:
    schema = sync_builtins(session)[0]
    rows = [
        CordRow("validation", 0, _jpeg(10), {"menu": {"nm": "A", "price": "1.000"}}),
        CordRow("validation", 1, _jpeg(11), {"total": {"total_price": "2.000"}}),
        CordRow("validation", 2, _jpeg(12), {}),
    ]

    stats = import_rows(session, storage, iter(rows), schema, limit=2)
    assert (stats.seen, stats.created, stats.skipped, stats.labelled) == (2, 2, 0, 2)

    again = import_rows(session, storage, iter(rows), schema)
    assert (again.seen, again.created, again.skipped) == (3, 1, 2)

    documents = session.scalars(select(Document).order_by(Document.external_id)).all()
    assert [d.external_id for d in documents] == [
        "cord-v2/validation/0000",
        "cord-v2/validation/0001",
        "cord-v2/validation/0002",
    ]
    assert all(d.split == "validation" and d.source == "cord" for d in documents)
    labels = session.scalars(select(GoldenLabel)).all()
    assert len(labels) == 3
    by_doc = {label.document_id: label.data for label in labels}
    assert by_doc[documents[0].id]["line_items"][0]["line_total"] == 1000.0
    assert by_doc[documents[1].id]["total"] == 2000.0


def test_remap_labels_recomputes_data_from_the_raw_annotation(
    session: Session, storage: LocalStorage
) -> None:
    schema = sync_builtins(session)[0]
    row = CordRow("validation", 0, _jpeg(30), {"total": {"total_price": "Rp. 111,000"}})
    import_rows(session, storage, iter([row]), schema)
    label = session.scalars(select(GoldenLabel)).one()
    assert label.raw == {"total": {"total_price": "Rp. 111,000"}}
    assert label.data["total"] == 111000.0

    label.data = {**label.data, "total": 111.0}  # what an older parser produced
    session.flush()
    assert remap_labels(session, schema) == 1
    assert session.scalars(select(GoldenLabel)).one().data["total"] == 111000.0
    assert remap_labels(session, schema) == 0
