import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldwise.db.models import Document
from fieldwise.documents.cord_import import CordRow, import_rows
from fieldwise.documents.ocr import FakeOcrProvider, OcrSpan
from fieldwise.documents.ocr_service import ocr_document
from fieldwise.evals.runner import labelled_documents
from fieldwise.gate.bundle import build_bundle, load_bundle
from fieldwise.schemas.registry import sync_builtins
from fieldwise.storage import LocalStorage

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cord"


def test_bundle_round_trip(session: Session, storage: LocalStorage, tmp_path: Path) -> None:
    schema = sync_builtins(session)[0]
    stem = "cord-v2_validation_0000"
    row = CordRow(
        "test",
        0,
        (FIXTURES / f"{stem}.jpg").read_bytes(),
        json.loads((FIXTURES / f"{stem}.json").read_text()),
    )
    import_rows(session, storage, iter([row]), schema)
    document = session.scalars(select(Document)).one()
    ocr_document(document, storage, FakeOcrProvider([OcrSpan("TOTAL", (100, 200, 300, 240), 0.9)]))

    out = tmp_path / "gate"
    assert build_bundle(session, storage, schema, out, limit=20) == 1
    manifest = json.loads((out / "manifest.json").read_text())
    entry = manifest["documents"][0]
    assert entry["external_id"] == "cord-v2/test/0000"
    assert entry["golden"]["total"] == 45500.0
    assert entry["ocr_words"][0]["box"] == [
        100,
        200,
        300,
        240,
    ]  # fixture is below the max edge: no scaling
    assert (out / entry["image"]).exists()

    # A second, empty database (simulated by deleting the document) loads the bundle back.
    session.delete(document)
    session.flush()
    other_storage = LocalStorage(tmp_path / "other")
    assert load_bundle(session, other_storage, schema, out) == 1
    assert load_bundle(session, other_storage, schema, out) == 0  # idempotent
    loaded = labelled_documents(session, schema, "test")
    assert len(loaded) == 1
    restored, golden = loaded[0]
    assert restored.external_id == "cord-v2/test/0000"
    assert restored.ocr_status == "done"
    assert restored.ocr_text == "TOTAL"
    assert golden["total"] == 45500.0
