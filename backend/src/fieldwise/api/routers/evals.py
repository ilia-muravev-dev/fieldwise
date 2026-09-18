import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from fieldwise.api.deps import DbSession
from fieldwise.api.models import EvalOut, EvalRequest, EvalResultOut, TaskAccepted
from fieldwise.config import get_settings
from fieldwise.db.models import Document, EvalResult, EvalRun, ExtractionRun
from fieldwise.evals.report import ordered_fields, render_comparison
from fieldwise.extraction.prompts.registry import PROMPTS
from fieldwise.worker.tasks import run_eval_task

router = APIRouter(prefix="/evals", tags=["evals"])


def _out(run: EvalRun) -> EvalOut:
    out = EvalOut.model_validate(run)
    out.field_order = ordered_fields(run, run.per_field) + ordered_fields(run, run.lists)
    return out


@router.get("", response_model=list[EvalOut])
def list_evals(db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[EvalOut]:
    runs = db.scalars(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(limit)).all()
    return [_out(r) for r in runs]


@router.get("/compare")
def compare(db: DbSession, ids: Annotated[list[uuid.UUID], Query()]) -> dict[str, object]:
    runs = [db.get(EvalRun, run_id) for run_id in ids]
    if any(r is None for r in runs):
        raise HTTPException(404, "eval run not found")
    found = [r for r in runs if r is not None]
    return {
        "runs": [_out(r).model_dump(mode="json") for r in found],
        "markdown": render_comparison(found),
    }


@router.get("/{eval_id}", response_model=EvalOut)
def get_eval(eval_id: uuid.UUID, db: DbSession) -> EvalOut:
    run = db.get(EvalRun, eval_id)
    if run is None:
        raise HTTPException(404, "eval run not found")
    return _out(run)


@router.get("/{eval_id}/results", response_model=list[EvalResultOut])
def get_results(eval_id: uuid.UUID, db: DbSession) -> list[EvalResultOut]:
    if db.get(EvalRun, eval_id) is None:
        raise HTTPException(404, "eval run not found")
    rows = db.execute(
        select(EvalResult, Document, ExtractionRun)
        .join(Document, Document.id == EvalResult.document_id)
        .join(ExtractionRun, ExtractionRun.id == EvalResult.extraction_run_id)
        .where(EvalResult.eval_run_id == eval_id)
        .order_by(Document.external_id, Document.name, EvalResult.rep)
    ).all()
    return [
        EvalResultOut(
            document_id=result.document_id,
            document_name=document.name,
            extraction_run_id=result.extraction_run_id,
            rep=result.rep,
            status=run.status,
            all_correct=(result.outcomes or {}).get("all_correct") if result.outcomes else None,
            outcomes=result.outcomes,
        )
        for result, document, run in rows
    ]


@router.post("", response_model=TaskAccepted, status_code=202)
def start_eval(body: EvalRequest) -> TaskAccepted:
    if body.prompt not in PROMPTS:
        raise HTTPException(422, f"unknown prompt {body.prompt!r}")
    if body.mode not in ("sync", "batch"):
        raise HTTPException(422, "mode must be sync or batch")
    settings = get_settings()
    config = {
        "schema": body.schema_name,
        "prompt": body.prompt,
        "model": body.model or settings.default_model,
        "effort": body.effort or settings.default_effort,
        "fewshot_k": body.fewshot_k,
        "use_ocr_text": body.use_ocr_text,
        "split": body.split,
        "limit": body.limit,
        "reps": body.reps,
        "mode": body.mode,
        "notes": body.notes,
    }
    task = run_eval_task.delay(config)
    return TaskAccepted(task_id=task.id)
