"""Command-line interface: database, schemas, ingestion, extraction, evals and reports."""

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import or_, select

from fieldwise import __version__
from fieldwise.config import get_settings
from fieldwise.db import migrate
from fieldwise.db.engine import get_engine, session_factory
from fieldwise.db.models import Document
from fieldwise.documents.cord_import import import_split
from fieldwise.documents.ocr import RapidOcrProvider
from fieldwise.documents.ocr_service import ocr_document, pending_documents
from fieldwise.logging import configure_logging
from fieldwise.schemas.registry import compile_builtin, sync_builtins
from fieldwise.storage import get_storage

app = typer.Typer(help="fieldwise — document extraction workbench.", no_args_is_help=True)
db_app = typer.Typer(help="Database migrations.", no_args_is_help=True)
schemas_app = typer.Typer(help="Extraction schemas.", no_args_is_help=True)
ingest_app = typer.Typer(help="Import documents and golden labels.", no_args_is_help=True)
ocr_app = typer.Typer(help="Run OCR over stored documents.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(schemas_app, name="schemas")
app.add_typer(ingest_app, name="ingest")
app.add_typer(ocr_app, name="ocr")
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
def db_upgrade(revision: str = "head") -> None:
    """Apply migrations up to REVISION (default: head)."""
    migrate.upgrade(get_engine(), revision)
    console.print(f"[green]database at {revision}[/green]")


@db_app.command("downgrade")
def db_downgrade(revision: str = "base") -> None:
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


@ocr_app.command("show")
def ocr_show(
    document: Annotated[str, typer.Argument(help="Document id, external id or name.")],
) -> None:
    """Print the OCR text of one document."""
    with session_factory()() as session:
        row = session.scalars(
            select(Document).where(or_(Document.external_id == document, Document.name == document))
        ).first()
        if row is None:
            try:
                row = session.get(Document, document)
            except Exception:  # not a UUID
                row = None
        if row is None:
            raise typer.BadParameter(f"no document {document!r}")
        console.print(f"[bold]{row.name}[/bold]  ocr_status={row.ocr_status}")
        console.print(row.ocr_text or "(no text)")


if __name__ == "__main__":
    app()
