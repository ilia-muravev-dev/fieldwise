"""One extraction in two halves — `prepare_extraction` builds the request and the pending run,
`finish_extraction` grades the response into it — so the eval runner can execute the middle step
in a thread pool or hand a whole set of requests to the Batches API. `run_extraction` is the
straight-through version."""

import json
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any

import jsonschema
import structlog
from sqlalchemy.orm import Session

from fieldwise.db.models import Document, ExtractionRun, Schema
from fieldwise.documents.ocr import OcrSpan, deserialise_spans
from fieldwise.extraction.builder import FewShotExample, build_request
from fieldwise.extraction.confidence import score_fields
from fieldwise.extraction.pricing import cost_usd
from fieldwise.extraction.prompts.registry import PromptSpec, get_prompt
from fieldwise.extraction.provider import LLMError, LLMProvider, LLMRequest, LLMResponse
from fieldwise.schemas.compiler import CompiledSchema, compile_schema
from fieldwise.storage import Storage
from fieldwise.values import parse_money

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


@dataclass
class PreparedExtraction:
    run: ExtractionRun
    request: LLMRequest
    document: Document
    compiled: CompiledSchema
    spans: list[OcrSpan]
    spec: PromptSpec
    rounds: list[dict[str, Any]] = field(default_factory=list)  # per round: text + data


class InvalidOutputError(ValueError):
    pass


def parse_output(text: str, output_schema: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise InvalidOutputError(f"not JSON: {error.msg} at {error.pos}") from error
    validator = jsonschema.Draft202012Validator(output_schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.path) or "<root>"
        raise InvalidOutputError(f"{where}: {first.message}")
    if not isinstance(data, dict):
        raise InvalidOutputError("the output is not an object")
    return data


def split_evidence(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """{"fields": ..., "evidence": ...} → (fields, evidence); plain results pass through."""
    if set(data) == {"fields", "evidence"} and isinstance(data["fields"], dict):
        evidence = {k: v for k, v in dict(data["evidence"]).items() if v not in (None, "")}
        return data["fields"], evidence
    return data, None


def inconsistency(result: dict[str, Any]) -> str | None:
    """Explains why the amounts do not add up, or None. Line totals must reach the subtotal, or
    the total when nothing sits between them; tolerance 1% (and at least one unit)."""
    items = result.get("line_items")
    if not isinstance(items, list) or not items:
        return None
    totals = [parse_money(item.get("line_total")) for item in items if isinstance(item, dict)]
    if any(t is None for t in totals):
        return None  # some line totals are not printed: nothing to reconcile
    items_sum = sum((t for t in totals if t is not None), Decimal(0))
    subtotal = parse_money(result.get("subtotal"))
    adjustments = [result.get(k) for k in ("discount", "service_charge", "tax")]
    target, name = (subtotal, "subtotal")
    if target is None and all(a in (None, "") for a in adjustments):
        target, name = (parse_money(result.get("total")), "total")
    if target is None:
        return None
    tolerance = max(abs(target) * Decimal("0.01"), Decimal(1))
    if abs(items_sum - target) <= tolerance:
        return None
    return f"the line totals add up to {items_sum} but the {name} is {target}"


def repair_request(prepared: PreparedExtraction, previous_text: str, reason: str) -> LLMRequest:
    """One more turn: the model sees its own answer and what does not add up."""
    follow_up = [
        {"role": "assistant", "content": previous_text},
        {
            "role": "user",
            "content": (
                f"Check again: {reason}. Re-read the receipt and return the corrected JSON object "
                "only — fix the line items or the amounts, whichever the receipt actually shows."
            ),
        },
    ]
    return replace(
        prepared.request,
        follow_up=follow_up,
        cache_key={**prepared.request.cache_key, "round": "repair"},
    )


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
        spec=spec,
    )


def finish_extraction(
    prepared: PreparedExtraction,
    outcome: LLMResponse | LLMError,
    *,
    batch_pricing: bool = False,
) -> ExtractionRun:
    """Grades one response into the run. Call it again with the repair round's response: usage
    adds up, and the later answer replaces the earlier one only when it parses."""
    run = prepared.run
    if isinstance(outcome, LLMError):
        return _fail(prepared, "failed", str(outcome))
    _record_usage(run, outcome, batch=batch_pricing)
    if outcome.truncated:
        return _fail(prepared, "truncated", "stop_reason=max_tokens")
    try:
        data = parse_output(outcome.text, prepared.request.output_schema)
    except InvalidOutputError as error:
        return _fail(prepared, "failed", f"invalid_output: {error}")
    is_repair = bool(prepared.rounds)
    fields, evidence = split_evidence(data)
    confidences, boxes = score_fields(fields, prepared.spans)
    run.result = fields
    run.evidence = evidence
    run.confidences = confidences
    run.boxes = {path: [list(b) for b in box_list] for path, box_list in boxes.items()}
    run.status = "succeeded"
    if is_repair:
        run.repair_rounds = len(prepared.rounds)
        run.error = None
    prepared.rounds.append({"text": outcome.text, "fields": fields})
    return run


def _fail(prepared: PreparedExtraction, status: str, message: str) -> ExtractionRun:
    """A failed round: the first one fails the run, a failed repair keeps the first answer."""
    run = prepared.run
    if prepared.rounds:
        run.error = f"repair skipped: {message}"
        return run
    run.status = status
    run.error = message
    log.warning("extraction.failed", document=prepared.document.name, status=status, error=message)
    return run


def pending_repair(prepared: PreparedExtraction) -> LLMRequest | None:
    """After a successful first round: the repair request when the spec asks for a check and
    the amounts do not add up; None otherwise (or once a repair has already run)."""
    run = prepared.run
    if (
        not prepared.spec.consistency_check
        or run.status != "succeeded"
        or len(prepared.rounds) != 1
    ):
        return None
    reason = inconsistency(run.result or {})
    if reason is None:
        return None
    return repair_request(prepared, prepared.rounds[0]["text"], reason)


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
    run = finish_extraction(
        prepared, _call(provider, prepared.request), batch_pricing=options.batch_pricing
    )
    repair = pending_repair(prepared)
    if repair is not None:
        finish_extraction(prepared, _call(provider, repair), batch_pricing=options.batch_pricing)
    session.flush()
    return run


def _call(provider: LLMProvider, request: LLMRequest) -> LLMResponse | LLMError:
    try:
        return provider.complete(request)
    except LLMError as error:
        return error


def _record_usage(run: ExtractionRun, response: LLMResponse, *, batch: bool) -> None:
    cost = (
        response.cost_usd
        if response.cost_usd is not None
        else cost_usd(run.model, response.usage, batch=batch)
    )
    run.input_tokens = (run.input_tokens or 0) + response.usage.input_tokens
    run.cache_write_tokens = (run.cache_write_tokens or 0) + response.usage.cache_write_tokens
    run.cache_read_tokens = (run.cache_read_tokens or 0) + response.usage.cache_read_tokens
    run.output_tokens = (run.output_tokens or 0) + response.usage.output_tokens
    run.cost_usd = (
        None if cost is None and run.cost_usd is None else (run.cost_usd or 0.0) + (cost or 0.0)
    )
    run.latency_ms = (run.latency_ms or 0) + response.latency_ms
    run.served_model = response.served_model
    run.request_id = response.request_id
