"""Background work: OCR + embedding after an upload, queued extractions, eval runs.
Every task opens its own session and commits its own outcome; failures are written to the row
the client is polling, so nothing is lost when a task dies."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from fieldwise.config import get_settings
from fieldwise.db.engine import session_factory
from fieldwise.db.models import Document, ExtractionRun, Schema
from fieldwise.documents.ocr import RapidOcrProvider
from fieldwise.documents.ocr_service import ocr_document
from fieldwise.evals.runner import EvalConfig, run_eval
from fieldwise.extraction.factory import build_provider
from fieldwise.extraction.pipeline import (
    ExtractionOptions,
    finish_extraction,
    prepare_extraction,
)
from fieldwise.extraction.prompts.registry import get_prompt
from fieldwise.extraction.provider import LLMError, LLMResponse
from fieldwise.retrieval.embeddings import FastEmbedder
from fieldwise.retrieval.fewshot import embed_documents, make_retriever
from fieldwise.storage import get_storage
from fieldwise.worker.app import celery_app

log = structlog.get_logger(__name__)

_ocr = RapidOcrProvider()
_embedder = FastEmbedder()


@celery_app.task(name="fieldwise.process_document")
def process_document(document_id: str) -> dict[str, Any]:
    """OCR the pages, then embed the text so the document can serve as a few-shot example."""
    with session_factory()() as session:
        document = session.get(Document, uuid.UUID(document_id))
        if document is None:
            return {"status": "missing"}
        try:
            ocr_document(document, get_storage(), _ocr)
            session.commit()
            embed_documents(session, _embedder, limit=None, force=False)
            session.commit()
        except Exception as error:
            session.commit()  # ocr_status=failed is already on the row
            log.warning("process_document.failed", document_id=document_id, error=str(error))
            return {"status": "failed", "error": str(error)}
        return {"status": document.ocr_status}


@celery_app.task(name="fieldwise.run_queued_extraction")
def run_queued_extraction(run_id: str, options: dict[str, Any]) -> dict[str, Any]:
    """Executes an ExtractionRun the API created in `queued` status."""
    settings = get_settings()
    with session_factory()() as session:
        run = session.get(ExtractionRun, uuid.UUID(run_id))
        if run is None:
            return {"status": "missing"}
        document = session.get(Document, run.document_id)
        schema = session.get(Schema, run.schema_id)
        if document is None or schema is None:
            run.status = "failed"
            run.error = "document or schema missing"
            session.commit()
            return {"status": "failed"}
        provider = build_provider(settings)
        extraction_options = ExtractionOptions(**options)
        spec = get_prompt(extraction_options.prompt)
        k = spec.fewshot_k if extraction_options.fewshot_k is None else extraction_options.fewshot_k
        examples = make_retriever(session, schema, _embedder)(document, k) if k else []
        try:
            prepared = prepare_extraction(
                session,
                get_storage(),
                document,
                schema=schema,
                options=extraction_options,
                provider_name=provider.name,
                examples=examples,
                run=run,
            )
            session.commit()
            outcome: LLMResponse | LLMError
            try:
                outcome = provider.complete(prepared.request)
            except LLMError as error:
                outcome = error
            finish_extraction(prepared, outcome)
        except Exception as error:
            run.status = "failed"
            run.error = f"worker: {error}"
            log.warning("run_queued_extraction.failed", run_id=run_id, error=str(error))
        session.commit()
        return {"status": run.status}


@celery_app.task(name="fieldwise.run_eval")
def run_eval_task(config: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    eval_config = EvalConfig(**config)
    with session_factory()() as session:
        provider = build_provider(settings)
        schema = (
            session.query(Schema)
            .filter(Schema.name == eval_config.schema)
            .order_by(Schema.version.desc())
            .first()
        )
        retriever = make_retriever(session, schema, _embedder) if schema else None
        try:
            run = run_eval(session, get_storage(), eval_config, provider, retriever=retriever)
            session.commit()
        except Exception as error:
            session.rollback()
            log.warning("run_eval.failed", error=str(error))
            return {"status": "failed", "error": str(error)}
        return {"status": run.status, "eval_run_id": str(run.id)}
