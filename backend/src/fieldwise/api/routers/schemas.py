from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fieldwise.api.deps import DbSession
from fieldwise.api.models import FieldMetaOut, SchemaOut
from fieldwise.db.models import Schema
from fieldwise.schemas.compiler import compile_schema
from fieldwise.schemas.registry import get_schema

router = APIRouter(prefix="/schemas", tags=["schemas"])


def to_out(schema: Schema) -> SchemaOut:
    compiled = compile_schema(schema.json_schema)
    return SchemaOut(
        id=schema.id,
        name=schema.name,
        version=schema.version,
        json_schema=schema.json_schema,
        fields=[FieldMetaOut(**f.to_dict()) for f in compiled.fields],
        created_at=schema.created_at,
    )


@router.get("", response_model=list[SchemaOut])
def list_schemas(db: DbSession) -> list[SchemaOut]:
    rows = db.scalars(select(Schema).order_by(Schema.name, Schema.version.desc())).all()
    latest: dict[str, Schema] = {}
    for row in rows:
        latest.setdefault(row.name, row)
    return [to_out(s) for s in latest.values()]


@router.get("/{name}", response_model=SchemaOut)
def get_one(name: str, db: DbSession, version: int | None = None) -> SchemaOut:
    schema = get_schema(db, name, version)
    if schema is None:
        raise HTTPException(404, f"schema {name!r} not found")
    return to_out(schema)
