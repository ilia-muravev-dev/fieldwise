import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldwise.db.models import EvalResult, ExtractionRun
from fieldwise.documents.cord_import import CordRow, import_rows
from fieldwise.documents.ocr import FakeOcrProvider
from fieldwise.documents.ocr_service import ocr_document
from fieldwise.evals.report import render_comparison, render_markdown, write_report
from fieldwise.evals.runner import EvalConfig, labelled_documents, run_eval
from fieldwise.extraction.factory import empty_answer
from fieldwise.extraction.provider import FakeProvider, LLMError, LLMRequest
from fieldwise.schemas.registry import sync_builtins
from fieldwise.storage import LocalStorage

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cord"
STEMS = ["cord-v2_validation_0000", "cord-v2_validation_0006", "cord-v2_validation_0008"]


@pytest.fixture
def labelled(session: Session, storage: LocalStorage) -> None:
    schema = sync_builtins(session)[0]
    rows = [
        CordRow(
            "test",
            i,
            (FIXTURES / f"{stem}.jpg").read_bytes(),
            json.loads((FIXTURES / f"{stem}.json").read_text()),
        )
        for i, stem in enumerate(STEMS)
    ]
    import_rows(session, storage, iter(rows), schema)
    for document, _ in labelled_documents(session, schema, "test"):
        ocr_document(document, storage, FakeOcrProvider())


def test_oracle_and_null_baseline(session: Session, storage: LocalStorage, labelled: None) -> None:
    schema = sync_builtins(session)[0]
    golden_by_sha = {
        d.external_id or d.sha256: g for d, g in labelled_documents(session, schema, "test")
    }
    oracle = FakeProvider(lambda req: golden_by_sha[req.cache_key["document"]])

    run = run_eval(session, storage, EvalConfig(model="claude-sonnet-5", concurrency=1), oracle)

    assert run.status == "done"
    assert (run.doc_count, run.succeeded, run.failed) == (3, 3, 0)
    assert run.overall_accuracy == 1.0
    assert run.value_accuracy == 1.0
    assert run.doc_exact_rate == 1.0
    assert run.lists["line_items"]["exact_rate"] == 1.0
    assert run.cost_usd is not None  # priced from the (fake) usage at Sonnet 5 rates
    assert run.p50_ms is not None
    assert session.scalars(select(EvalResult).where(EvalResult.eval_run_id == run.id)).all()

    null = run_eval(
        session, storage, EvalConfig(model="null", concurrency=1), FakeProvider(empty_answer)
    )
    assert null.value_accuracy == 0.0
    assert null.doc_exact_rate == 0.0
    assert null.overall_accuracy is not None
    assert null.overall_accuracy > 0.0  # null-null matches count in the strict number


def test_failures_go_to_the_sidecar_not_the_score(
    session: Session, storage: LocalStorage, labelled: None
) -> None:
    schema = sync_builtins(session)[0]
    docs = labelled_documents(session, schema, "test")
    golden_by_sha = {d.external_id or d.sha256: g for d, g in docs}
    first_sha = docs[0][0].external_id or docs[0][0].sha256

    def flaky(request: LLMRequest) -> dict[str, object]:
        if request.cache_key["document"] == first_sha:
            raise LLMError("rate_limit", "429", retryable=True)
        return golden_by_sha[request.cache_key["document"]]

    run = run_eval(session, storage, EvalConfig(model="flaky", concurrency=2), FakeProvider(flaky))

    assert (run.succeeded, run.failed, run.truncated) == (2, 1, 0)
    assert run.overall_accuracy == 1.0  # the failed document is not in the denominator
    assert run.errors == [
        {"document": docs[0][0].name, "status": "failed", "error": "rate_limit: 429"}
    ]
    statuses = session.scalars(select(ExtractionRun.status)).all()
    assert sorted(statuses) == ["failed", "succeeded", "succeeded"]


def test_batch_mode_and_reports(
    session: Session, storage: LocalStorage, labelled: None, tmp_path: Path
) -> None:
    schema = sync_builtins(session)[0]
    golden_by_sha = {
        d.external_id or d.sha256: g for d, g in labelled_documents(session, schema, "test")
    }
    provider = FakeProvider(lambda req: golden_by_sha[req.cache_key["document"]])
    statuses: list[str] = []

    run = run_eval(
        session,
        storage,
        EvalConfig(model="oracle", mode="batch", reps=2, notes="batch test"),
        provider,
        on_batch_status=lambda status, n: statuses.append(status),
    )

    assert statuses == ["ended"]
    assert run.mode == "batch"
    assert run.reps == 2
    assert run.succeeded == 6
    assert run.p50_ms is None  # no per-request latency in batch mode
    assert run.overall_accuracy == 1.0

    markdown = render_markdown(run)
    assert "| `total` | money | 6 | 100.0% |" in markdown
    assert "batch test" in markdown
    comparison = render_comparison([run, run])
    assert comparison.startswith("| Metric | v1 / oracle | v1 / oracle |")
    path = write_report(tmp_path, run)
    assert path.exists()
    assert json.loads(path.with_suffix(".json").read_text())["overall_accuracy"] == 1.0
