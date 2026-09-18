import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from fieldwise.documents.cord_import import map_gt_parse
from fieldwise.documents.ocr import RapidOcrProvider
from fieldwise.documents.ocr_service import ocr_document
from fieldwise.documents.service import create_document
from fieldwise.extraction.factory import empty_answer
from fieldwise.extraction.pipeline import ExtractionOptions, run_extraction
from fieldwise.extraction.provider import FakeProvider, LLMError, LLMRequest
from fieldwise.schemas.registry import sync_builtins
from fieldwise.storage import LocalStorage

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cord"
STEM = "cord-v2_validation_0000"


@pytest.fixture
def receipt(session: Session, storage: LocalStorage) -> tuple[object, object, dict[str, object]]:
    schema = sync_builtins(session)[0]
    document = create_document(
        session,
        storage,
        data=(FIXTURES / f"{STEM}.jpg").read_bytes(),
        name=STEM,
        source="upload",
    )
    ocr_document(document, storage, RapidOcrProvider())
    golden = map_gt_parse(json.loads((FIXTURES / f"{STEM}.json").read_text()))
    return document, schema, golden


def test_successful_extraction_is_grounded_and_priced(
    session: Session, storage: LocalStorage, receipt: tuple[object, object, dict[str, object]]
) -> None:
    document, schema, golden = receipt
    provider = FakeProvider(lambda req: golden)

    run = run_extraction(
        session,
        storage,
        document,  # type: ignore[arg-type]
        schema=schema,  # type: ignore[arg-type]
        options=ExtractionOptions(prompt="v1", model="claude-sonnet-5", effort="low"),
        provider=provider,
    )

    assert run.status == "succeeded"
    assert run.result == golden
    assert run.provider == "fake"
    assert run.prompt_version == "v1"
    assert run.use_ocr_text is False
    assert run.confidences is not None
    assert run.confidences["total"] == 1.0
    assert run.boxes is not None
    assert "total" in run.boxes
    assert run.cost_usd is not None
    assert run.cost_usd > 0
    assert run.served_model == "claude-sonnet-5"
    request: LLMRequest = provider.requests[0]
    assert request.cache_key["document"] == document.sha256  # type: ignore[attr-defined]
    assert request.cache_key["schema"] == "receipt@1"


def test_invalid_output_fails_the_run(
    session: Session, storage: LocalStorage, receipt: tuple[object, object, dict[str, object]]
) -> None:
    document, schema, _ = receipt
    run = run_extraction(
        session,
        storage,
        document,  # type: ignore[arg-type]
        schema=schema,  # type: ignore[arg-type]
        options=ExtractionOptions(),
        provider=FakeProvider(lambda req: '{"total": "not a number"'),
    )
    assert run.status == "failed"
    assert run.error is not None
    assert run.error.startswith("invalid_output: not JSON")

    run = run_extraction(
        session,
        storage,
        document,  # type: ignore[arg-type]
        schema=schema,  # type: ignore[arg-type]
        options=ExtractionOptions(),
        provider=FakeProvider(lambda req: {"total": "text"}),
    )
    assert run.status == "failed"
    assert run.error is not None
    assert "invalid_output" in run.error


def test_truncation_and_provider_errors_are_recorded_not_scored(
    session: Session, storage: LocalStorage, receipt: tuple[object, object, dict[str, object]]
) -> None:
    document, schema, _ = receipt
    truncated = run_extraction(
        session,
        storage,
        document,  # type: ignore[arg-type]
        schema=schema,  # type: ignore[arg-type]
        options=ExtractionOptions(),
        provider=FakeProvider(empty_answer, stop_reason="max_tokens"),
    )
    assert truncated.status == "truncated"
    assert truncated.result is None
    assert truncated.output_tokens is not None

    def explode(request: LLMRequest) -> dict[str, object]:
        raise LLMError("rate_limit", "429", retryable=True)

    failed = run_extraction(
        session,
        storage,
        document,  # type: ignore[arg-type]
        schema=schema,  # type: ignore[arg-type]
        options=ExtractionOptions(),
        provider=FakeProvider(explode),
    )
    assert failed.status == "failed"
    assert failed.error == "rate_limit: 429"
    assert failed.input_tokens is None
