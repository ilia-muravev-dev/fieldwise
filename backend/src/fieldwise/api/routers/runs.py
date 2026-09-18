import uuid

from fastapi import APIRouter, HTTPException

from fieldwise.api.deps import DbSession
from fieldwise.api.models import RunOut
from fieldwise.db.models import ExtractionRun

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: uuid.UUID, db: DbSession) -> RunOut:
    run = db.get(ExtractionRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return RunOut.model_validate(run)
