"""Command-line interface: database, schemas, ingestion, extraction, evals and reports."""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from fieldwise import __version__
from fieldwise.config import get_settings
from fieldwise.db import migrate
from fieldwise.db.engine import get_engine, session_factory
from fieldwise.db.models import Document, EvalRun
from fieldwise.documents.cord_import import import_split
from fieldwise.documents.ocr import RapidOcrProvider
from fieldwise.documents.ocr_service import ocr_document, pending_documents
from fieldwise.evals.report import print_summary, render_comparison, write_report
from fieldwise.evals.runner import EvalConfig, labelled_documents, run_eval
from fieldwise.extraction.factory import build_provider, describe
from fieldwise.extraction.pipeline import ExtractionOptions, prepare_extraction, run_extraction
from fieldwise.extraction.pricing import price_for
from fieldwise.logging import configure_logging
from fieldwise.schemas.registry import compile_builtin, get_schema, sync_builtins
from fieldwise.storage import get_storage

app = typer.Typer(help="fieldwise — document extraction workbench.", no_args_is_help=True)
db_app = typer.Typer(help="Database migrations.", no_args_is_help=True)
schemas_app = typer.Typer(help="Extraction schemas.", no_args_is_help=True)
ingest_app = typer.Typer(help="Import documents and golden labels.", no_args_is_help=True)
ocr_app = typer.Typer(help="Run OCR over stored documents.", no_args_is_help=True)
eval_app = typer.Typer(help="Measure a configuration on a labelled split.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(schemas_app, name="schemas")
app.add_typer(ingest_app, name="ingest")
app.add_typer(ocr_app, name="ocr")
app.add_typer(eval_app, name="eval")
console = Console()


@app.callback()
def main() -> None:
    """fieldwise — document extraction workbench."""
    configure_logging(get_settings().log_level)


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"fieldwise {__version__}")


@db_app.command("upgrade")
def db_upgrade(revision: Annotated[str, typer.Argument()] = "head") -> None:
    """Apply migrations up to REVISION (default: head)."""
    migrate.upgrade(get_engine(), revision)
    console.print(f"[green]database at {revision}[/green]")


@db_app.command("downgrade")
def db_downgrade(revision: Annotated[str, typer.Argument()] = "base") -> None:
    """Roll migrations back down to REVISION (default: base — drops everything)."""
    migrate.downgrade(get_engine(), revision)
    console.print(f"[yellow]database at {revision}[/yellow]")


@schemas_app.command("sync")
def schemas_sync() -> None:
    """Store the built-in schemas (a new version is created when a schema changed)."""
    with session_factory()() as session:
        stored = sync_builtins(session)
        session.commit()
        for schema in stored:
            console.print(f"{schema.name} v{schema.version}  ({len(schema.field_meta)} fields)")


@schemas_app.command("show")
def schemas_show(name: str) -> None:
    """Print the fields of a built-in schema with their matchers."""
    compiled = compile_builtin(name)
    table = Table(title=f"schema {compiled.name}")
    table.add_column("field")
    table.add_column("type")
    table.add_column("matcher")
    table.add_column("description", overflow="fold")
    for field in compiled.fields:
        table.add_row(field.path, field.type, field.matcher, field.description)
    console.print(table)


@ingest_app.command("cord")
def ingest_cord(
    split: Annotated[
        list[str] | None, typer.Option(help="Dataset split(s): test, validation, train.")
    ] = None,
    limit: Annotated[int | None, typer.Option(help="Stop after N rows per split.")] = None,
) -> None:
    """Import CORD v2 receipts (CC BY 4.0) with golden labels for the receipt schema."""
    with session_factory()() as session:
        for name in split or ["test", "validation"]:
            console.print(f"[bold]cord-v2/{name}[/bold]: downloading and importing …")
            stats = import_split(session, get_storage(), name, limit=limit)
            console.print(
                f"  seen {stats.seen} · created {stats.created} · skipped {stats.skipped}"
                f" · labelled {stats.labelled} · errors {len(stats.errors)}"
            )
            for error in stats.errors[:10]:
                console.print(f"  [red]{error}[/red]")


@ocr_app.command("run")
def ocr_run(
    split: Annotated[str | None, typer.Option(help="Only documents of this split.")] = None,
    limit: Annotated[int | None, typer.Option(help="Stop after N documents.")] = None,
    force: Annotated[bool, typer.Option(help="Re-run OCR on documents already done.")] = False,
) -> None:
    """OCR every document whose text is missing (RapidOCR, on the CPU, ~0.3 s per page)."""
    provider = RapidOcrProvider()
    storage = get_storage()
    done = failed = 0
    with session_factory()() as session:
        documents = pending_documents(session, split=split, limit=limit, force=force)
        console.print(f"{len(documents)} document(s) to process")
        for document in documents:
            try:
                ocr_document(document, storage, provider)
                session.commit()
                done += 1
            except Exception as error:  # keep going, report at the end
                session.commit()  # persists ocr_status = failed
                failed += 1
                console.print(f"[red]{document.name}: {error}[/red]")
    console.print(f"[green]done {done}[/green] · [red]failed {failed}[/red]")


def _find_document(session: Session, reference: str) -> Document:
    row = session.scalars(
        select(Document).where(or_(Document.external_id == reference, Document.name == reference))
    ).first()
    if row is None:
        try:
            row = session.get(Document, reference)
        except Exception:  # not a UUID
            row = None
    if row is None:
        raise typer.BadParameter(f"no document {reference!r}")
    return row


@ocr_app.command("show")
def ocr_show(
    document: Annotated[str, typer.Argument(help="Document id, external id or name.")],
) -> None:
    """Print the OCR text of one document."""
    with session_factory()() as session:
        row = _find_document(session, document)
        console.print(f"[bold]{row.name}[/bold]  ocr_status={row.ocr_status}")
        console.print(row.ocr_text or "(no text)")


@app.command()
def extract(
    document: Annotated[str, typer.Argument(help="Document id, external id or name.")],
    *,
    schema: Annotated[str, typer.Option(help="Schema name.")] = "receipt",
    prompt: Annotated[str, typer.Option(help="Prompt version.")] = "v1",
    model: Annotated[str | None, typer.Option(help="Model id (default from settings).")] = None,
    effort: Annotated[str | None, typer.Option(help="low|medium|high|xhigh|max.")] = None,
    provider: Annotated[str | None, typer.Option(help="anthropic | fake.")] = None,
    cassette: Annotated[str | None, typer.Option(help="off | record | replay.")] = None,
    ocr_text: Annotated[bool | None, typer.Option(help="Force OCR text on/off.")] = None,
) -> None:
    """Extract one document and print the result with tokens, cost and latency."""
    settings = get_settings()
    llm = build_provider(
        settings,
        provider_name=provider,
        cassette_mode=cassette,  # type: ignore[arg-type]
    )
    options = ExtractionOptions(
        prompt=prompt,
        model=model or settings.default_model,
        effort=effort or settings.default_effort,
        use_ocr_text=ocr_text,
    )
    with session_factory()() as session:
        row = _find_document(session, document)
        schema_row = get_schema(session, schema)
        if schema_row is None:
            raise typer.BadParameter(f"schema {schema!r} is not in the database")
        run = run_extraction(
            session, get_storage(), row, schema=schema_row, options=options, provider=llm
        )
        session.commit()
        console.print(
            f"[bold]{row.name}[/bold] · {describe(llm)} · {run.model} · prompt {run.prompt_version}"
            f" · effort {run.effort} · status [bold]{run.status}[/bold]"
        )
        if run.result is not None:
            console.print_json(json.dumps(run.result))
        if run.error:
            console.print(f"[red]{run.error}[/red]")
        console.print(
            f"tokens in {run.input_tokens} (cache write {run.cache_write_tokens}, read "
            f"{run.cache_read_tokens}) · out {run.output_tokens} · cost ${run.cost_usd} · "
            f"{run.latency_ms} ms · served by {run.served_model} · run {run.id}"
        )


REPORTS_DIR = Path(__file__).resolve().parents[3] / "docs" / "evals"


def _estimate(
    session: Session, storage: object, config: EvalConfig, provider: object
) -> str | None:
    """Counts the tokens of one real request and scales it; None when the provider cannot."""
    estimate = getattr(provider, "estimate_input_tokens", None)
    price = price_for(config.model)
    if estimate is None or price is None:
        return None
    schema_row = get_schema(session, config.schema)
    if schema_row is None:
        return None
    documents = labelled_documents(session, schema_row, config.split, limit=1)
    if not documents:
        return None
    sample = prepare_extraction(
        session,
        storage,  # type: ignore[arg-type]
        documents[0][0],
        schema=schema_row,
        options=config.options(),
        provider_name="estimate",
    )
    session.expunge(sample.run)
    input_tokens = estimate(sample.request)
    if input_tokens is None:
        return None
    docs = len(labelled_documents(session, schema_row, config.split, config.limit))
    per_doc = (input_tokens * price.input + 700 * price.output) / 1_000_000
    total = per_doc * docs * config.reps * (0.5 if config.mode == "batch" else 1.0)
    return (
        f"~{input_tokens} input tokens per document; {docs} docs x {config.reps} rep(s)"
        f"{' at batch prices' if config.mode == 'batch' else ''} ≈ ${total:.2f}"
    )


@eval_app.command("run")
def eval_run_command(
    *,
    schema: Annotated[str, typer.Option(help="Schema name.")] = "receipt",
    prompt: Annotated[str, typer.Option(help="Prompt version.")] = "v1",
    model: Annotated[str | None, typer.Option(help="Model id.")] = None,
    effort: Annotated[str | None, typer.Option(help="low|medium|high|xhigh|max.")] = None,
    split: Annotated[str, typer.Option(help="Split to measure.")] = "test",
    limit: Annotated[int | None, typer.Option(help="First N documents only.")] = None,
    reps: Annotated[int, typer.Option(help="Repetitions per document.")] = 1,
    batch: Annotated[bool, typer.Option(help="Use the Batches API (50% price).")] = False,
    concurrency: Annotated[int, typer.Option(help="Parallel requests in sync mode.")] = 4,
    fewshot: Annotated[int | None, typer.Option(help="Override the few-shot k.")] = None,
    ocr_text: Annotated[bool | None, typer.Option(help="Force OCR text on/off.")] = None,
    provider: Annotated[str | None, typer.Option(help="anthropic | openai | fake.")] = None,
    cassette: Annotated[str | None, typer.Option(help="off | record | replay.")] = None,
    notes: Annotated[str, typer.Option(help="Free text stored with the run.")] = "",
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the cost confirmation.")] = False,
    write: Annotated[bool, typer.Option(help="Write the Markdown report to docs/evals.")] = True,
) -> None:
    """Run a configuration over a labelled split and report per-field accuracy, cost, latency."""
    settings = get_settings()
    llm = build_provider(
        settings,
        provider_name=provider,
        cassette_mode=cassette,  # type: ignore[arg-type]
    )
    config = EvalConfig(
        schema=schema,
        prompt=prompt,
        model=model or settings.default_model,
        effort=effort or settings.default_effort,
        fewshot_k=fewshot,
        use_ocr_text=ocr_text,
        split=split,
        limit=limit,
        reps=reps,
        mode="batch" if batch else "sync",
        concurrency=concurrency,
        notes=notes,
    )
    storage = get_storage()
    with session_factory()() as session:
        if not yes:
            estimate = _estimate(session, storage, config, llm)
            session.rollback()
            console.print(f"[bold]{describe(llm)}[/bold] · {config.model} · prompt {config.prompt}")
            console.print(
                estimate or "cost estimate unavailable for this provider (free or unknown)"
            )
            if not typer.confirm("Run it?", default=False):
                raise typer.Exit(code=1)
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as bar:
            task = bar.add_task("extracting", total=None)

            def progress(done: int, total: int) -> None:
                bar.update(task, completed=done, total=total)

            def on_status(status: str, processing: int) -> None:
                bar.update(task, description=f"batch {status} ({processing} processing)")

            run = run_eval(
                session, storage, config, llm, progress=progress, on_batch_status=on_status
            )
        session.commit()
        print_summary(console, run)
        if write:
            path = write_report(REPORTS_DIR, run)
            console.print(f"report: {path.relative_to(REPORTS_DIR.parents[1])}")


@eval_app.command("list")
def eval_list(limit: Annotated[int, typer.Option(help="Most recent N runs.")] = 20) -> None:
    """List eval runs."""
    table = Table(title="eval runs")
    for column in (
        "id",
        "when",
        "prompt",
        "model",
        "k",
        "ocr",
        "split",
        "docs",
        "strict",
        "docs ok",
        "$/doc",
        "p50",
    ):
        table.add_column(column)
    with session_factory()() as session:
        runs = session.scalars(
            select(EvalRun).order_by(EvalRun.created_at.desc()).limit(limit)
        ).all()
        for run in runs:
            table.add_row(
                str(run.id)[:8],
                run.created_at.strftime("%m-%d %H:%M"),
                run.prompt_version,
                run.model,
                str(run.fewshot_k),
                "on" if run.use_ocr_text else "off",
                run.split,
                f"{run.succeeded}/{run.doc_count * run.reps}",
                "—" if run.overall_accuracy is None else f"{run.overall_accuracy * 100:.1f}%",
                "—" if run.value_accuracy is None else f"{run.value_accuracy * 100:.1f}%",
                "—" if run.doc_exact_rate is None else f"{run.doc_exact_rate * 100:.1f}%",
                "—" if run.cost_per_doc is None else f"{run.cost_per_doc:.4f}",
                "—" if run.p50_ms is None else f"{run.p50_ms}",
            )
    console.print(table)


def _find_eval(session: Session, reference: str) -> EvalRun:
    runs = session.scalars(select(EvalRun).order_by(EvalRun.created_at.desc())).all()
    matches = [r for r in runs if str(r.id).startswith(reference)]
    if len(matches) != 1:
        raise typer.BadParameter(f"{len(matches)} eval runs match {reference!r}")
    return matches[0]


@eval_app.command("show")
def eval_show(run: Annotated[str, typer.Argument(help="Eval run id (prefix).")]) -> None:
    """Print one eval run's per-field table."""
    with session_factory()() as session:
        print_summary(console, _find_eval(session, run))


@eval_app.command("compare")
def eval_compare(
    runs: Annotated[list[str], typer.Argument(help="Eval run ids (prefixes), in column order.")],
    write: Annotated[bool, typer.Option(help="Also write docs/evals/compare-<ids>.md")] = False,
) -> None:
    """Print a Markdown comparison table across eval runs (the README table)."""
    with session_factory()() as session:
        found = [_find_eval(session, r) for r in runs]
        markdown = render_comparison(found)
    console.print(markdown)
    if write:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORTS_DIR / ("compare-" + "-".join(str(r.id)[:8] for r in found) + ".md")
        path.write_text(markdown, encoding="utf-8")
        console.print(f"written: {path.relative_to(REPORTS_DIR.parents[1])}")


if __name__ == "__main__":
    app()
