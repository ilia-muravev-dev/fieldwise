"""Built-in schemas shipped with the package, and their upsert into the database."""

import json
from importlib import resources
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from fieldwise.db.models import Schema
from fieldwise.schemas.compiler import CompiledSchema, compile_schema

BUILTIN_PACKAGE = "fieldwise.schemas.builtin"


def load_builtin(name: str) -> dict[str, Any]:
    text = resources.files(BUILTIN_PACKAGE).joinpath(f"{name}.json").read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def builtin_names() -> list[str]:
    return sorted(
        p.name.removesuffix(".json")
        for p in resources.files(BUILTIN_PACKAGE).iterdir()
        if p.name.endswith(".json")
    )


def compile_builtin(name: str) -> CompiledSchema:
    return compile_schema(load_builtin(name))


def get_schema(session: Session, name: str, version: int | None = None) -> Schema | None:
    stmt = select(Schema).where(Schema.name == name)
    stmt = (
        stmt.where(Schema.version == version)
        if version is not None
        else stmt.order_by(Schema.version.desc())
    )
    return session.scalars(stmt).first()


def upsert_schema(session: Session, authored: dict[str, Any]) -> Schema:
    """Stores the authored schema as a new version when it differs from the latest one."""
    compiled = compile_schema(authored)
    latest = get_schema(session, compiled.name)
    if latest is not None and latest.json_schema == authored:
        if json.dumps(latest.json_schema) != json.dumps(authored):
            latest.json_schema = authored  # same schema, restore the authored key order
            flag_modified(latest, "json_schema")  # dict equality would hide the reorder
            session.flush()
        return latest
    schema = Schema(
        name=compiled.name,
        version=(latest.version + 1) if latest else 1,
        json_schema=authored,
        field_meta=compiled.field_meta_dict(),
    )
    session.add(schema)
    session.flush()
    return schema


def sync_builtins(session: Session) -> list[Schema]:
    return [upsert_schema(session, load_builtin(name)) for name in builtin_names()]
