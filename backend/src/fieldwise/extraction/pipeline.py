"""One extraction in two halves — `prepare_extraction` builds the request and the pending run,
`finish_extraction` grades the response into it — so the eval runner can execute the middle step
in a thread pool or hand a whole set of requests to the Batches API. `run_extraction` is the
straight-through version."""

import json
from dataclasses import dataclass, replace
from typing import Any

import jsonschema
import structlog
from sqlalchemy.orm import Session

from fieldwise.db.models import Document, ExtractionRun, Schema
from fieldwise.documents.ocr import OcrSpan, deserialise_spans
from fieldwise.extraction.builder import FewShotExample, build_request
from fieldwise.extraction.confidence import score_fields
from fieldwise.extraction.pricing import cost_usd
from fieldwise.extraction.prompts.registry import get_prompt
from fieldwise.extraction.provider import LLMError, LLMProvider, LLMRequest, LLMResponse
from fieldwise.schemas.compiler import CompiledSchema, compile_schema
from fieldwise.storage import Storage

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ExtractionOptions:
    prompt: str = "v1"
    model: str = "claude-sonnet-5"
    effort: str = "low"
    fewshot_k: int | None = None  # None → the prompt version's default
    use_ocr_text: bool | None = None  # None → the prompt version's default
    max_tokens: int = 4096
    batch_pricing: bool = False


@dataclass(frozen=True)
class PreparedExtraction:
    run: ExtractionRun
    request: LLMRequest
    document: Document
    compiled: CompiledSchema
    spans: list[OcrSpan]


class InvalidOutputError(ValueError):
    pass


def parse_output(text: str, strict_schema: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise InvalidOutputError(f"not JSON: {error.msg} at {error.pos}") from error
    validator = jsonschema.Draft202012Validator(strict_schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.path) or "<root>"
        raise InvalidOutputError(f"{where}: {first.message}")
    if not isinstance(data, dict):
        raise InvalidOutputError("the output is not an object")
    return data


def document_spans(document: Document) -> list[OcrSpan]:
    return deserialise_spans(document.ocr_words or [])


def prepare_extraction(
    session: Session,
    storage: Storage,
    document: Document,
    *,
    schema: Schema,
    options: ExtractionOptions,
    provider_name: str,
    examples: list[FewShotExample] | None = None,
    run: ExtractionRun | None = None,
) -> PreparedExtraction:
    spec = get_prompt(options.prompt)
    compiled = compile_schema(schema.json_schema)
    fewshot_k = spec.fewshot_k if options.fewshot_k is None else options.fewshot_k
    use_ocr_text = spec.use_ocr_text if options.use_ocr_text is None else options.use_ocr_text
    examples = (examples or [])[:fewshot_k]

    if run is None:
        run = ExtractionRun(document_id=document.id, schema_id=schema.id)
        session.add(run)
    run.prompt_version = spec.name
    run.model = options.model
    run.effort = options.effort
    run.fewshot_k = len(examples)
    run.use_ocr_text = use_ocr_text
    run.provider = provider_name
    run.status = "running"
    run.fewshot_document_ids = [e.document_id for e in examples]
    session.flush()

    request = build_request(
        spec=replace(spec, use_ocr_text=use_ocr_text),
        compiled=compiled,
        authored_schema=schema.json_schema,
        page_jpegs=[storage.get(str(page["key"])) for page in document.pages],
        ocr_text=document.ocr_text,
        examples=examples,
        model=options.model,
        effort=options.effort,
        max_tokens=options.max_tokens,
        cache_key={
            # Stable across re-imports and downscaled fixture copies of dataset documents.
            "document": document.external_id or document.sha256,
            "schema": f"{schema.name}@{schema.version}",
            "ocr_text": str(use_ocr_text),
        },
    )
    return PreparedExtraction(
        run=run,
        request=request,
        document=document,
        compiled=compiled,
        spans=document_spans(document),
    )


def finish_extraction(
    prepared: PreparedExtraction,
    outcome: LLMResponse | LLMError,
    *,
    batch_pricing: bool = False,
) -> ExtractionRun:
    run = prepared.run
    if isinstance(outcome, LLMError):
        run.status = "failed"
        run.error = str(outcome)
        log.warning("extraction.failed", document=prepared.document.name, error=str(outcome))
        return run
    _record_usage(run, outcome, batch=batch_pricing)
    if outcome.truncated:
        run.status = "truncated"
        run.error = "stop_reason=max_tokens"
        return run
    try:
        data = parse_output(outcome.text, prepared.compiled.strict)
    except InvalidOutputError as error:
        run.status = "failed"
        run.error = f"invalid_output: {error}"
        log.warning("extraction.invalid_output", document=prepared.document.name, error=str(error))
        return run
    confidences, boxes = score_fields(data, prepared.spans)
    run.result = data
    run.confidences = confidences
    run.boxes = {path: [list(b) for b in box_list] for path, box_list in boxes.items()}
    run.status = "succeeded"
    return run


def run_extraction(
    session: Session,
    storage: Storage,
    document: Document,
    *,
    schema: Schema,
    options: ExtractionOptions,
    provider: LLMProvider,
    examples: list[FewShotExample] | None = None,
) -> ExtractionRun:
    prepared = prepare_extraction(
        session,
        storage,
        document,
        schema=schema,
        options=options,
        provider_name=provider.name,
        examples=examples,
    )
    outcome: LLMResponse | LLMError
    try:
        outcome = provider.complete(prepared.request)
    except LLMError as error:
        outcome = error
    run = finish_extraction(prepared, outcome, batch_pricing=options.batch_pricing)
    session.flush()
    return run


def _record_usage(run: ExtractionRun, response: LLMResponse, *, batch: bool) -> None:
    run.input_tokens = response.usage.input_tokens
    run.cache_write_tokens = response.usage.cache_write_tokens
    run.cache_read_tokens = response.usage.cache_read_tokens
    run.output_tokens = response.usage.output_tokens
    run.cost_usd = (
        response.cost_usd
        if response.cost_usd is not None
        else cost_usd(run.model, response.usage, batch=batch)
    )
    run.latency_ms = response.latency_ms
    run.served_model = response.served_model
    run.request_id = response.request_id
