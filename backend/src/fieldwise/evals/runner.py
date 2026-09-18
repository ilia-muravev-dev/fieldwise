"""Runs one configuration over a labelled split and turns the graded outcomes into numbers.

Rules the runner keeps (see docs/adr/0001 and CLAUDE.md):
- failed and truncated extractions go to the error sidecar; they never count as wrong answers
- accuracy denominators are graded fields only; cost comes from the usage the API reported
- latency is the final request's, sync mode only (batch mode has no per-request latency)
- documents are graded against their latest golden label (a reviewer's correction beats the
  dataset label)"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldwise.db.models import Document, EvalResult, EvalRun, GoldenLabel, Schema
from fieldwise.evals.matchers import DocumentOutcome, grade_document
from fieldwise.evals.stats import Proportion, percentile
from fieldwise.extraction.builder import FewShotExample
from fieldwise.extraction.pipeline import (
    ExtractionOptions,
    PreparedExtraction,
    finish_extraction,
    prepare_extraction,
)
from fieldwise.extraction.prompts.registry import get_prompt
from fieldwise.extraction.provider import LLMError, LLMProvider, LLMRequest, LLMResponse
from fieldwise.schemas.compiler import CompiledSchema, compile_schema

Retriever = Callable[[Document, int], list[FewShotExample]]
Progress = Callable[[int, int], None]


@dataclass(frozen=True)
class EvalConfig:
    schema: str = "receipt"
    prompt: str = "v1"
    model: str = "claude-sonnet-5"
    effort: str = "low"
    fewshot_k: int | None = None
    use_ocr_text: bool | None = None
    split: str = "test"
    limit: int | None = None
    reps: int = 1
    mode: Literal["sync", "batch"] = "sync"
    concurrency: int = 4
    max_tokens: int = 4096
    notes: str = ""

    def options(self) -> ExtractionOptions:
        return ExtractionOptions(
            prompt=self.prompt,
            model=self.model,
            effort=self.effort,
            fewshot_k=self.fewshot_k,
            use_ocr_text=self.use_ocr_text,
            max_tokens=self.max_tokens,
            batch_pricing=self.mode == "batch",
        )


def labelled_documents(
    session: Session, schema: Schema, split: str, limit: int | None = None
) -> list[tuple[Document, dict[str, Any]]]:
    """Documents of the split that have a golden label; corrections win over dataset labels."""
    stmt = (
        select(Document, GoldenLabel)
        .join(GoldenLabel, GoldenLabel.document_id == Document.id)
        .where(Document.split == split, GoldenLabel.schema_id == schema.id)
        .order_by(Document.external_id, Document.name, GoldenLabel.source)
    )
    chosen: dict[Any, tuple[Document, dict[str, Any]]] = {}
    for document, label in session.execute(stmt):
        current = chosen.get(document.id)
        if current is None or label.source == "correction":
            chosen[document.id] = (document, label.data)
    ordered = list(chosen.values())
    return ordered[:limit] if limit else ordered


@dataclass
class Aggregate:
    per_field: dict[str, Any]
    lists: dict[str, Any]
    overall: Proportion  # strict: correct + null_match over every graded leaf
    lenient: Proportion  # strict plus fuzzy text matches
    value: Proportion  # leaves whose golden has a value: correct over those only
    doc_exact: Proportion


def aggregate(compiled: CompiledSchema, outcomes: list[DocumentOutcome]) -> Aggregate:
    counters: dict[str, Counter[str]] = {
        f.path: Counter() for f in compiled.fields if f.matcher not in ("list", "object")
    }
    list_totals: dict[str, dict[str, int]] = {
        f.path: {"exact": 0, "golden": 0, "predicted": 0, "matched": 0, "docs": 0}
        for f in compiled.fields
        if f.matcher == "list"
    }
    all_correct = 0
    for outcome in outcomes:
        all_correct += int(outcome.all_correct)
        for path, results in outcome.leaves.items():
            counters.setdefault(path, Counter()).update(results)
        for path, lo in outcome.lists.items():
            totals = list_totals.setdefault(
                path, {"exact": 0, "golden": 0, "predicted": 0, "matched": 0, "docs": 0}
            )
            totals["docs"] += 1
            totals["exact"] += int(lo.exact)
            totals["golden"] += lo.golden_count
            totals["predicted"] += lo.predicted_count
            totals["matched"] += lo.matched_items

    per_field: dict[str, Any] = {}
    strict_correct = strict_total = lenient_correct = value_correct = value_total = 0
    by_path = {f.path: f for f in compiled.fields}
    for path, counter in counters.items():
        total = sum(counter.values())
        correct = counter["correct"] + counter["null_match"]
        with_value = total - counter["null_match"] - counter["spurious"]
        strict = Proportion(correct, total)
        lenient = Proportion(correct + counter["fuzzy"], total)
        value = Proportion(counter["correct"], with_value)
        strict_correct += correct
        lenient_correct += correct + counter["fuzzy"]
        strict_total += total
        value_correct += counter["correct"]
        value_total += with_value
        per_field[path] = {
            "matcher": by_path[path].matcher if path in by_path else "text",
            "n": total,
            "accuracy": strict.value,
            "ci": strict.wilson(),
            "lenient": lenient.value,
            "value_n": with_value,
            "value_accuracy": value.value,
            "counts": dict(counter),
        }
    lists: dict[str, Any] = {}
    for path, totals in list_totals.items():
        exact = Proportion(totals["exact"], totals["docs"])
        lists[path] = {
            "docs": totals["docs"],
            "exact_rate": exact.value,
            "ci": exact.wilson(),
            "item_precision": totals["matched"] / totals["predicted"]
            if totals["predicted"]
            else None,
            "item_recall": totals["matched"] / totals["golden"] if totals["golden"] else None,
            "golden_items": totals["golden"],
            "predicted_items": totals["predicted"],
        }
    return Aggregate(
        per_field=per_field,
        lists=lists,
        overall=Proportion(strict_correct, strict_total),
        lenient=Proportion(lenient_correct, strict_total),
        value=Proportion(value_correct, value_total),
        doc_exact=Proportion(all_correct, len(outcomes)),
    )


def run_eval(
    session: Session,
    storage: Any,
    config: EvalConfig,
    provider: LLMProvider,
    *,
    retriever: Retriever | None = None,
    progress: Progress | None = None,
    on_batch_status: Callable[[str, int], None] | None = None,
) -> EvalRun:
    schema = session.scalars(
        select(Schema).where(Schema.name == config.schema).order_by(Schema.version.desc())
    ).first()
    if schema is None:
        raise ValueError(f"schema {config.schema!r} is not in the database")
    compiled = compile_schema(schema.json_schema)
    documents = labelled_documents(session, schema, config.split, config.limit)
    if not documents:
        raise ValueError(f"no labelled documents in split {config.split!r}")

    options = config.options()
    eval_run = EvalRun(
        schema_id=schema.id,
        prompt_version=config.prompt,
        model=config.model,
        effort=config.effort,
        fewshot_k=0,
        use_ocr_text=True,
        provider=provider.name,
        split=config.split,
        mode=config.mode,
        notes=config.notes,
        doc_count=len(documents),
        reps=config.reps,
    )
    session.add(eval_run)
    session.flush()

    spec = get_prompt(config.prompt)
    fewshot_k = spec.fewshot_k if options.fewshot_k is None else options.fewshot_k
    prepared: list[tuple[PreparedExtraction, dict[str, Any], int]] = []
    for document, golden in documents:
        examples = retriever(document, fewshot_k) if retriever and fewshot_k else []
        for rep in range(1, config.reps + 1):
            item = prepare_extraction(
                session,
                storage,
                document,
                schema=schema,
                options=options,
                provider_name=provider.name,
                examples=examples,
            )
            prepared.append((item, golden, rep))
    if prepared:
        eval_run.fewshot_k = prepared[0][0].run.fewshot_k
        eval_run.use_ocr_text = prepared[0][0].run.use_ocr_text
    session.flush()

    requests = [item.request for item, _, _ in prepared]
    outcomes = _execute(provider, requests, config, progress=progress, on_status=on_batch_status)

    _grade_and_summarise(
        session, eval_run, compiled=compiled, prepared=prepared, outcomes=outcomes, config=config
    )
    session.flush()
    return eval_run


def _grade_and_summarise(
    session: Session,
    eval_run: EvalRun,
    *,
    compiled: CompiledSchema,
    prepared: list[tuple[PreparedExtraction, dict[str, Any], int]],
    outcomes: list[LLMResponse | LLMError],
    config: EvalConfig,
) -> None:
    graded: list[DocumentOutcome] = []
    latencies: list[float] = []
    costs: list[float] = []
    counts = Counter[str]()
    errors: list[dict[str, Any]] = []
    for (item, golden, rep), outcome in zip(prepared, outcomes, strict=True):
        run = finish_extraction(item, outcome, batch_pricing=config.mode == "batch")
        counts[run.status] += 1
        result = EvalResult(
            eval_run_id=eval_run.id,
            document_id=item.document.id,
            extraction_run_id=run.id,
            rep=rep,
        )
        if run.status == "succeeded" and run.result is not None:
            doc_outcome = grade_document(compiled, golden, run.result)
            graded.append(doc_outcome)
            result.outcomes = doc_outcome.to_dict()
            if run.latency_ms:
                latencies.append(float(run.latency_ms))
            if run.cost_usd is not None:
                costs.append(run.cost_usd)
        else:
            errors.append(
                {"document": item.document.name, "status": run.status, "error": run.error}
            )
        session.add(result)

    agg = aggregate(compiled, graded)
    eval_run.succeeded = counts["succeeded"]
    eval_run.truncated = counts["truncated"]
    eval_run.failed = counts["failed"]
    eval_run.per_field = agg.per_field
    eval_run.lists = agg.lists
    eval_run.overall_accuracy = agg.overall.value
    eval_run.lenient_accuracy = agg.lenient.value
    eval_run.value_accuracy = agg.value.value
    eval_run.doc_exact_rate = agg.doc_exact.value
    eval_run.cost_usd = round(sum(costs), 6) if costs else None
    eval_run.cost_per_doc = round(sum(costs) / len(costs), 6) if costs else None
    if config.mode == "sync" and latencies:
        eval_run.p50_ms = int(percentile(latencies, 50) or 0)
        eval_run.p95_ms = int(percentile(latencies, 95) or 0)
    eval_run.errors = errors
    eval_run.status = "done"
    eval_run.finished_at = datetime.now(UTC)


def _execute(
    provider: LLMProvider,
    requests: list[LLMRequest],
    config: EvalConfig,
    *,
    progress: Progress | None,
    on_status: Callable[[str, int], None] | None,
) -> list[LLMResponse | LLMError]:
    if config.mode == "batch":
        batch = getattr(provider, "complete_batch", None)
        if batch is None:
            raise ValueError(f"provider {provider.name} does not support batch mode")
        outcomes: list[LLMResponse | LLMError] = batch(requests, on_status=on_status)
        if progress:
            progress(len(requests), len(requests))
        return outcomes

    def one(request: LLMRequest) -> LLMResponse | LLMError:
        try:
            return provider.complete(request)
        except LLMError as error:
            return error

    done = 0
    results: list[LLMResponse | LLMError] = []
    if config.concurrency <= 1:
        for request in requests:
            results.append(one(request))
            done += 1
            if progress:
                progress(done, len(requests))
        return results
    with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        for outcome in pool.map(one, requests):
            results.append(outcome)
            done += 1
            if progress:
                progress(done, len(requests))
    return results
