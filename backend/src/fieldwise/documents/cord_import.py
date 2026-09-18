"""Imports CORD v2 (naver-clova-ix/cord-v2, CC BY 4.0) receipts as documents with golden labels.

CORD's `gt_parse` is mapped onto the built-in `receipt` schema; keys the schema does not model
(`menu.num`, `sub_nm`, `void_menu`, ...) are dropped. Ground truth is normalised once at import
with the same parsers the eval matchers use, so a golden "60.000" and a predicted 60000 agree.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import structlog
from huggingface_hub import HfApi, hf_hub_download
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldwise.db.models import Document, GoldenLabel, Schema
from fieldwise.documents.service import create_document
from fieldwise.schemas.registry import get_schema
from fieldwise.storage import Storage
from fieldwise.values import parse_int, parse_money

CORD_REPO = "naver-clova-ix/cord-v2"
SPLITS = ("train", "validation", "test")

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CordRow:
    split: str
    index: int
    image: bytes
    gt_parse: dict[str, Any]

    @property
    def external_id(self) -> str:
        return f"cord-v2/{self.split}/{self.index:04d}"


@dataclass
class ImportStats:
    seen: int = 0
    created: int = 0
    skipped: int = 0
    labelled: int = 0
    errors: list[str] = field(default_factory=list)


def list_split_files(split: str) -> list[str]:
    files = HfApi().list_repo_files(CORD_REPO, repo_type="dataset")
    return sorted(f for f in files if f.startswith(f"data/{split}-") and f.endswith(".parquet"))


def download_split(split: str) -> list[Path]:
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}; expected one of {SPLITS}")
    return [
        Path(hf_hub_download(CORD_REPO, filename=name, repo_type="dataset"))
        for name in list_split_files(split)
    ]


def iter_rows(split: str, paths: list[Path]) -> Iterator[CordRow]:
    index = 0
    for path in paths:
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=8, columns=["image", "ground_truth"]):
            for record in batch.to_pylist():
                gt = json.loads(record["ground_truth"])
                yield CordRow(
                    split=split,
                    index=index,
                    image=record["image"]["bytes"],
                    gt_parse=gt.get("gt_parse") or {},
                )
                index += 1


def _first_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        merged: dict[str, Any] = {}
        for item in value:
            if isinstance(item, dict):
                merged = {**item, **merged}  # earlier entries win
        return merged
    return {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = " ".join(str(v) for v in value if v is not None)
    text = " ".join(str(value).split())
    return text or None


def _money(value: Any) -> float | None:
    parsed = parse_money(value)
    return float(parsed) if parsed is not None else None


def map_gt_parse(gt_parse: dict[str, Any]) -> dict[str, Any]:
    """CORD gt_parse → receipt golden data (schema field order, normalised values)."""
    menu = gt_parse.get("menu") or []
    if isinstance(menu, dict):
        menu = [menu]
    items = []
    for raw in menu:
        if not isinstance(raw, dict):
            continue
        quantity = parse_int(raw.get("cnt"))
        line_total = _money(raw.get("price"))
        if line_total is None:  # some receipts only print the item subtotal
            line_total = _money(raw.get("itemsubtotal"))
        items.append(
            {
                "name": _text(raw.get("nm")),
                "quantity": quantity if quantity is not None else 1,
                "unit_price": _money(raw.get("unitprice")),
                "line_total": line_total,
            }
        )
    sub_total = _first_dict(gt_parse.get("sub_total"))
    total = _first_dict(gt_parse.get("total"))
    return {
        "line_items": items,
        "subtotal": _money(sub_total.get("subtotal_price")),
        "discount": _money(sub_total.get("discount_price")),
        "service_charge": _money(sub_total.get("service_price")),
        "tax": _money(sub_total.get("tax_price")),
        "total": _money(total.get("total_price")),
        "cash_paid": _money(total.get("cashprice")),
        "change": _money(total.get("changeprice")),
        "card_paid": _money(total.get("creditcardprice")),
        "item_count": parse_int(total.get("menuqty_cnt")),
    }


def import_rows(
    session: Session,
    storage: Storage,
    rows: Iterator[CordRow],
    schema: Schema,
    limit: int | None = None,
) -> ImportStats:
    stats = ImportStats()
    for row in rows:
        if limit is not None and stats.seen >= limit:
            break
        stats.seen += 1
        existing = session.scalars(
            select(Document).where(Document.external_id == row.external_id)
        ).first()
        if existing is not None:
            stats.skipped += 1
            continue
        try:
            document = create_document(
                session,
                storage,
                data=row.image,
                name=row.external_id,
                source="cord",
                split=row.split,
                external_id=row.external_id,
            )
            has_label = session.scalars(
                select(GoldenLabel.id).where(
                    GoldenLabel.document_id == document.id,
                    GoldenLabel.schema_id == schema.id,
                    GoldenLabel.source == "dataset",
                )
            ).first()
            if has_label is not None:  # same bytes already imported under another id
                stats.skipped += 1
                session.commit()
                continue
            session.add(
                GoldenLabel(
                    document_id=document.id,
                    schema_id=schema.id,
                    data=map_gt_parse(row.gt_parse),
                    raw=row.gt_parse,
                    source="dataset",
                )
            )
            session.commit()
            stats.created += 1
            stats.labelled += 1
        except Exception as error:
            session.rollback()
            stats.errors.append(f"{row.external_id}: {error}")
            log.warning("cord_import.row_failed", external_id=row.external_id, error=str(error))
    return stats


def import_split(
    session: Session, storage: Storage, split: str, limit: int | None = None
) -> ImportStats:
    schema = get_schema(session, "receipt")
    if schema is None:
        raise RuntimeError("receipt schema missing from the database; run `fieldwise schemas sync`")
    paths = download_split(split)
    return import_rows(session, storage, iter_rows(split, paths), schema, limit=limit)


def remap_labels(session: Session, schema: Schema) -> int:
    """Re-runs the mapper over stored raw annotations (after a mapper or parser fix)."""
    labels = session.scalars(
        select(GoldenLabel).where(
            GoldenLabel.schema_id == schema.id, GoldenLabel.source == "dataset"
        )
    ).all()
    changed = 0
    for label in labels:
        if label.raw is None:
            continue
        data = map_gt_parse(label.raw)
        if data != label.data:
            label.data = data
            changed += 1
    session.flush()
    return changed
