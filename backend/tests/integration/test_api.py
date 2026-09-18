import json
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from fieldwise.api import deps
from fieldwise.api.app import create_app
from fieldwise.api.routers import documents as documents_router
from fieldwise.api.routers import evals as evals_router
from fieldwise.db.models import Document
from fieldwise.documents.cord_import import map_gt_parse
from fieldwise.documents.ocr import FakeOcrProvider, OcrSpan
from fieldwise.documents.ocr_service import ocr_document
from fieldwise.evals.runner import EvalConfig, labelled_documents, run_eval
from fieldwise.extraction.pipeline import ExtractionOptions, run_extraction
from fieldwise.extraction.provider import FakeProvider
from fieldwise.schemas.registry import sync_builtins
from fieldwise.storage import LocalStorage

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cord"


class Delayed:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def delay(self, *args: Any) -> Any:
        self.calls.append(args)
        return type("Task", (), {"id": "task-1"})()


@pytest.fixture
def api(
    session: Session, storage: LocalStorage, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Delayed, Delayed, Delayed]]:
    sync_builtins(session)
    session.flush()
    app = create_app()
    app.dependency_overrides[deps._db] = lambda: session
    app.dependency_overrides[deps._storage] = lambda: storage
    process, extract, evaluate = Delayed(), Delayed(), Delayed()
    monkeypatch.setattr(documents_router, "process_document", process)
    monkeypatch.setattr(documents_router, "run_queued_extraction", extract)
    monkeypatch.setattr(evals_router, "run_eval_task", evaluate)
    with TestClient(app) as client:
        yield client, process, extract, evaluate


def _jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (200, 300), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_meta_endpoints(api: tuple[TestClient, Delayed, Delayed, Delayed]) -> None:
    client = api[0]
    assert client.get("/health").json()["status"] == "ok"
    prompts = client.get("/prompts").json()
    assert [p["name"] for p in prompts] == ["v1", "v2", "v3"]
    assert prompts[2]["fewshot_k"] == 3
    assert any(m["id"] == "claude-sonnet-5" for m in client.get("/models").json())


def test_schemas(api: tuple[TestClient, Delayed, Delayed, Delayed]) -> None:
    client = api[0]
    listed = client.get("/schemas").json()
    assert [s["name"] for s in listed] == ["receipt"]
    one = client.get("/schemas/receipt").json()
    assert one["version"] == 1
    assert any(
        f["path"] == "line_items[].line_total" and f["matcher"] == "money" for f in one["fields"]
    )
    assert client.get("/schemas/nope").status_code == 404


def test_document_lifecycle(
    api: tuple[TestClient, Delayed, Delayed, Delayed], session: Session
) -> None:
    client, process, extract, _ = api

    created = client.post("/documents", files={"file": ("r.jpg", _jpeg(), "image/jpeg")})
    assert created.status_code == 201, created.text
    doc = created.json()
    assert doc["ocr_status"] == "pending"
    assert doc["has_golden"] is False
    assert process.calls == [(doc["id"],)]

    listed = client.get("/documents", params={"limit": 10}).json()
    assert listed["total"] == 1
    assert listed["items"][0]["name"] == "r.jpg"

    detail = client.get(f"/documents/{doc['id']}").json()
    assert detail["pages"][0]["url"].endswith("/pages/1")
    page = client.get(detail["pages"][0]["url"])
    assert page.headers["content-type"] == "image/jpeg"
    assert page.content.startswith(b"\xff\xd8")
    assert client.get(f"/documents/{doc['id']}/pages/9").status_code == 404

    row = session.get(Document, __import__("uuid").UUID(doc["id"]))
    ocr_document(row, api_storage(client), FakeOcrProvider([OcrSpan("TOTAL", (1, 2, 30, 12), 0.9)]))  # type: ignore[arg-type]
    session.flush()
    spans = client.get(f"/documents/{doc['id']}/ocr").json()
    assert spans == [{"page": 1, "text": "TOTAL", "box": [1, 2, 30, 12], "conf": 0.9, "words": []}]

    queued = client.post(f"/documents/{doc['id']}/extract", json={"prompt": "v2"})
    assert queued.status_code == 202, queued.text
    run = queued.json()
    assert run["status"] == "queued"
    assert extract.calls[0][0] == run["id"]
    assert extract.calls[0][1]["prompt"] == "v2"
    assert client.get(f"/runs/{run['id']}").json()["status"] == "queued"
    assert client.post(f"/documents/{doc['id']}/extract", json={"prompt": "v9"}).status_code == 422

    assert client.get(f"/documents/{doc['id']}/golden").status_code == 404
    saved = client.put(
        f"/documents/{doc['id']}/golden", json={"data": {"total": 1.0, "line_items": []}}
    )
    assert saved.status_code == 200
    assert saved.json()["source"] == "correction"
    assert client.get(f"/documents/{doc['id']}").json()["has_golden"] is True
    again = client.put(
        f"/documents/{doc['id']}/golden", json={"data": {"total": 2.0, "line_items": []}}
    )
    assert again.json()["data"]["total"] == 2.0


def api_storage(client: TestClient) -> LocalStorage:
    override = client.app.dependency_overrides[deps._storage]  # type: ignore[attr-defined]
    storage: LocalStorage = override()
    return storage


def test_rejects_garbage_uploads(api: tuple[TestClient, Delayed, Delayed, Delayed]) -> None:
    client = api[0]
    assert (
        client.post("/documents", files={"file": ("x.bin", b"hello", "text/plain")}).status_code
        == 415
    )


def test_evals_endpoints(
    api: tuple[TestClient, Delayed, Delayed, Delayed], session: Session, storage: LocalStorage
) -> None:
    client, _, _, evaluate = api
    schema = sync_builtins(session)[0]
    from fieldwise.documents.cord_import import CordRow, import_rows  # noqa: PLC0415

    stem = "cord-v2_validation_0000"
    row = CordRow(
        "test",
        0,
        (FIXTURES / f"{stem}.jpg").read_bytes(),
        json.loads((FIXTURES / f"{stem}.json").read_text()),
    )
    import_rows(session, storage, iter([row]), schema)
    golden_by_sha = {
        d.external_id or d.sha256: g for d, g in labelled_documents(session, schema, "test")
    }
    run = run_eval(
        session,
        storage,
        EvalConfig(model="claude-sonnet-5", concurrency=1),
        FakeProvider(lambda req: golden_by_sha[req.cache_key["document"]]),
    )
    session.flush()

    listed = client.get("/evals").json()
    assert listed[0]["id"] == str(run.id)
    assert listed[0]["overall_accuracy"] == 1.0
    assert listed[0]["field_order"][0] == "line_items[].name"
    one = client.get(f"/evals/{run.id}").json()
    assert one["per_field"]["total"]["accuracy"] == 1.0
    results = client.get(f"/evals/{run.id}/results").json()
    assert results[0]["all_correct"] is True
    compared = client.get("/evals/compare", params={"ids": [str(run.id), str(run.id)]}).json()
    assert compared["markdown"].startswith("| Metric |")
    assert len(compared["runs"]) == 2

    started = client.post("/evals", json={"prompt": "v2", "limit": 5, "notes": "from the api"})
    assert started.status_code == 202
    assert started.json()["task_id"] == "task-1"
    assert evaluate.calls[0][0]["prompt"] == "v2"
    assert client.post("/evals", json={"prompt": "v9"}).status_code == 422
    assert client.get(f"/evals/{run.id}".replace(str(run.id)[:8], "00000000")).status_code == 404


def test_run_extraction_result_is_served(
    api: tuple[TestClient, Delayed, Delayed, Delayed], session: Session, storage: LocalStorage
) -> None:
    client = api[0]
    schema = sync_builtins(session)[0]
    from fieldwise.documents.service import create_document  # noqa: PLC0415

    document = create_document(
        session,
        storage,
        data=(FIXTURES / "cord-v2_validation_0000.jpg").read_bytes(),
        name="r",
        source="upload",
    )
    golden = map_gt_parse(json.loads((FIXTURES / "cord-v2_validation_0000.json").read_text()))
    run = run_extraction(
        session,
        storage,
        document,
        schema=schema,
        options=ExtractionOptions(),
        provider=FakeProvider(lambda req: golden),
    )
    served = client.get(f"/runs/{run.id}").json()
    assert served["status"] == "succeeded"
    assert served["result"]["total"] == golden["total"]
    detail = client.get(f"/documents/{document.id}").json()
    assert detail["latest_run"]["id"] == str(run.id)
    assert detail["runs"][0]["status"] == "succeeded"
