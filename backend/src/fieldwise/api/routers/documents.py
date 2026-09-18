import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from fieldwise.api.deps import Blobs, DbSession
from fieldwise.api.models import (
    DocumentDetail,
    DocumentList,
    DocumentOut,
    ExtractRequest,
    GoldenIn,
    GoldenOut,
    OcrSpanOut,
    PageOut,
    RunOut,
    RunSummary,
)
from fieldwise.config import get_settings
from fieldwise.db.models import Document, ExtractionRun, GoldenLabel
from fieldwise.documents.render import UnsupportedDocumentError
from fieldwise.documents.service import create_document
from fieldwise.extraction.prompts.registry import PROMPTS
from fieldwise.schemas.registry import get_schema
from fieldwise.worker.tasks import process_document, run_queued_extraction

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _latest_golden(db: Session, document_id: uuid.UUID) -> GoldenLabel | None:
    labels = db.scalars(
        select(GoldenLabel)
        .where(GoldenLabel.document_id == document_id)
        .order_by(GoldenLabel.created_at.desc())
    ).all()
    corrections = [label for label in labels if label.source == "correction"]
    return corrections[0] if corrections else (labels[0] if labels else None)


def _latest_run(db: Session, document_id: uuid.UUID) -> ExtractionRun | None:
    return db.scalars(
        select(ExtractionRun)
        .where(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
    ).first()


def _document_out(db: Session, document: Document) -> DocumentOut:
    run = _latest_run(db, document.id)
    return DocumentOut(
        id=document.id,
        name=document.name,
        source=document.source,
        split=document.split,
        mime=document.mime,
        page_count=document.page_count,
        ocr_status=document.ocr_status,
        has_golden=_latest_golden(db, document.id) is not None,
        latest_run=RunSummary.model_validate(run) if run else None,
        created_at=document.created_at,
    )


def _get_document(db: Session, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "document not found")
    return document


@router.get("", response_model=DocumentList)
def list_documents(
    db: DbSession,
    split: str | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentList:
    stmt = select(Document)
    if split:
        stmt = stmt.where(Document.split == split)
    if q:
        stmt = stmt.where(or_(Document.name.ilike(f"%{q}%"), Document.external_id.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Document.created_at.desc()).offset(offset).limit(limit)).all()
    return DocumentList(items=[_document_out(db, d) for d in rows], total=total)


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    db: DbSession, blobs: Blobs, file: Annotated[UploadFile, File()]
) -> DocumentOut:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file larger than 25 MB")
    try:
        document = create_document(
            db, blobs, data=data, name=file.filename or "upload", source="upload"
        )
    except UnsupportedDocumentError as error:
        raise HTTPException(415, str(error)) from error
    db.commit()
    if document.ocr_status != "done":
        process_document.delay(str(document.id))
    return _document_out(db, document)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, db: DbSession) -> DocumentDetail:
    document = _get_document(db, document_id)
    golden = _latest_golden(db, document.id)
    runs = db.scalars(
        select(ExtractionRun)
        .where(ExtractionRun.document_id == document.id)
        .order_by(ExtractionRun.created_at.desc())
        .limit(20)
    ).all()
    base = _document_out(db, document)
    return DocumentDetail(
        **base.model_dump(),
        pages=[
            PageOut(
                page=int(p["page"]),
                width=int(p["width"]),
                height=int(p["height"]),
                url=f"/documents/{document.id}/pages/{p['page']}",
            )
            for p in document.pages
        ],
        ocr_text=document.ocr_text,
        golden=GoldenOut(source=golden.source, data=golden.data, created_at=golden.created_at)
        if golden
        else None,
        runs=[RunSummary.model_validate(r) for r in runs],
    )


@router.get("/{document_id}/pages/{page}")
def get_page(document_id: uuid.UUID, page: int, db: DbSession, blobs: Blobs) -> Response:
    document = _get_document(db, document_id)
    for record in document.pages:
        if int(record["page"]) == page:
            return Response(
                blobs.get(str(record["key"])),
                media_type="image/jpeg",
                headers={"Cache-Control": "private, max-age=3600"},
            )
    raise HTTPException(404, "page not found")


@router.get("/{document_id}/ocr", response_model=list[OcrSpanOut])
def get_ocr(document_id: uuid.UUID, db: DbSession) -> list[OcrSpanOut]:
    document = _get_document(db, document_id)
    return [OcrSpanOut(**span) for span in (document.ocr_words or [])]


@router.get("/{document_id}/runs", response_model=list[RunOut])
def list_runs(document_id: uuid.UUID, db: DbSession) -> list[RunOut]:
    _get_document(db, document_id)
    runs = db.scalars(
        select(ExtractionRun)
        .where(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc())
    ).all()
    return [RunOut.model_validate(r) for r in runs]


@router.post("/{document_id}/extract", response_model=RunOut, status_code=202)
def extract(document_id: uuid.UUID, body: ExtractRequest, db: DbSession) -> RunOut:
    document = _get_document(db, document_id)
    schema = get_schema(db, body.schema_name)
    if schema is None:
        raise HTTPException(404, f"schema {body.schema_name!r} not found")
    if body.prompt not in PROMPTS:
        raise HTTPException(422, f"unknown prompt {body.prompt!r}")
    settings = get_settings()
    options = {
        "prompt": body.prompt,
        "model": body.model or settings.default_model,
        "effort": body.effort or settings.default_effort,
        "fewshot_k": body.fewshot_k,
        "use_ocr_text": body.use_ocr_text,
    }
    run = ExtractionRun(
        document_id=document.id,
        schema_id=schema.id,
        prompt_version=body.prompt,
        model=str(options["model"]),
        effort=str(options["effort"]),
        provider=settings.llm_provider,
        status="queued",
    )
    db.add(run)
    db.commit()
    run_queued_extraction.delay(str(run.id), options)
    return RunOut.model_validate(run)


@router.get("/{document_id}/golden", response_model=GoldenOut)
def get_golden(document_id: uuid.UUID, db: DbSession) -> GoldenOut:
    _get_document(db, document_id)
    golden = _latest_golden(db, document_id)
    if golden is None:
        raise HTTPException(404, "no golden label")
    return GoldenOut(source=golden.source, data=golden.data, created_at=golden.created_at)


@router.put("/{document_id}/golden", response_model=GoldenOut)
def put_golden(
    document_id: uuid.UUID, body: GoldenIn, db: DbSession, schema_name: str = "receipt"
) -> GoldenOut:
    """Stores a reviewer's correction; it becomes the document's golden label."""
    document = _get_document(db, document_id)
    schema = get_schema(db, schema_name)
    if schema is None:
        raise HTTPException(404, f"schema {schema_name!r} not found")
    existing = db.scalars(
        select(GoldenLabel).where(
            GoldenLabel.document_id == document.id,
            GoldenLabel.schema_id == schema.id,
            GoldenLabel.source == "correction",
        )
    ).first()
    if existing is None:
        existing = GoldenLabel(
            document_id=document.id, schema_id=schema.id, data=body.data, source="correction"
        )
        db.add(existing)
    else:
        existing.data = body.data
    db.commit()
    return GoldenOut(source=existing.source, data=existing.data, created_at=existing.created_at)
