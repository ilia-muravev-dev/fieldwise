"""The eval gate's fixture bundle: a handful of labelled test documents (downscaled page
images, OCR spans, golden labels) that CI loads into a fresh database and re-scores against
recorded model responses. No model is called and no dataset is downloaded."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldwise.db.models import Document, GoldenLabel, Schema
from fieldwise.documents.render import downscale_jpeg
from fieldwise.documents.service import create_document
from fieldwise.evals.runner import labelled_documents
from fieldwise.storage import Storage

BUNDLE_MAX_EDGE = 1000


@dataclass(frozen=True)
class GateBaseline:
    prompt: str
    model: str
    overall_accuracy: float | None
    value_accuracy: float | None
    doc_exact_rate: float | None
    per_field: dict[str, float | None]
    lists: dict[str, float | None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "model": self.model,
            "overall_accuracy": self.overall_accuracy,
            "value_accuracy": self.value_accuracy,
            "doc_exact_rate": self.doc_exact_rate,
            "per_field": self.per_field,
            "lists": self.lists,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GateBaseline:
        return cls(
            prompt=str(data["prompt"]),
            model=str(data["model"]),
            overall_accuracy=data.get("overall_accuracy"),
            value_accuracy=data.get("value_accuracy"),
            doc_exact_rate=data.get("doc_exact_rate"),
            per_field=dict(data.get("per_field", {})),
            lists=dict(data.get("lists", {})),
        )


def build_bundle(
    session: Session,
    storage: Storage,
    schema: Schema,
    out: Path,
    *,
    split: str = "test",
    limit: int = 20,
) -> int:
    """Writes manifest.json and images/ for the first `limit` labelled documents of the split."""
    (out / "images").mkdir(parents=True, exist_ok=True)
    entries = []
    for document, golden in labelled_documents(session, schema, split, limit):
        if not document.external_id or not document.pages:
            continue
        page = document.pages[0]
        jpeg = downscale_jpeg(storage.get(str(page["key"])), BUNDLE_MAX_EDGE)
        stem = document.external_id.replace("/", "_")
        (out / "images" / f"{stem}.jpg").write_bytes(jpeg)
        scale = BUNDLE_MAX_EDGE / max(int(page["width"]), int(page["height"]))
        scale = min(scale, 1.0)
        spans = [
            {
                **span,
                "box": [round(v * scale) for v in span["box"]],
                "words": [
                    {**w, "box": [round(v * scale) for v in w["box"]]}
                    for w in span.get("words", [])
                ],
            }
            for span in (document.ocr_words or [])
        ]
        entries.append(
            {
                "external_id": document.external_id,
                "split": split,
                "image": f"images/{stem}.jpg",
                "golden": golden,
                "ocr_text": document.ocr_text,
                "ocr_words": spans,
            }
        )
    (out / "manifest.json").write_text(
        json.dumps({"schema": schema.name, "documents": entries}, indent=1, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return len(entries)


def load_bundle(session: Session, storage: Storage, schema: Schema, bundle: Path) -> int:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    loaded = 0
    for entry in manifest["documents"]:
        existing = session.scalars(
            select(Document).where(Document.external_id == entry["external_id"])
        ).first()
        if existing is not None:
            continue
        document = create_document(
            session,
            storage,
            data=(bundle / entry["image"]).read_bytes(),
            name=entry["external_id"],
            source="cord",
            split=entry["split"],
            external_id=entry["external_id"],
        )
        document.ocr_text = entry.get("ocr_text")
        document.ocr_words = entry.get("ocr_words") or []
        document.ocr_status = "done"
        session.add(
            GoldenLabel(
                document_id=document.id, schema_id=schema.id, data=entry["golden"], source="dataset"
            )
        )
        loaded += 1
    session.flush()
    return loaded


def compare_to_baseline(
    current: GateBaseline, baseline: GateBaseline, tolerance: float
) -> list[str]:
    """Regressions larger than `tolerance` (absolute accuracy points), as human-readable lines."""
    problems: list[str] = []

    def check(name: str, before: float | None, after: float | None) -> None:
        if before is None or after is None:
            return
        if after < before - tolerance:
            problems.append(f"{name}: {before * 100:.1f}% → {after * 100:.1f}%")

    check("overall_accuracy", baseline.overall_accuracy, current.overall_accuracy)
    check("value_accuracy", baseline.value_accuracy, current.value_accuracy)
    check("doc_exact_rate", baseline.doc_exact_rate, current.doc_exact_rate)
    for path, before in baseline.per_field.items():
        check(path, before, current.per_field.get(path))
    for path, before in baseline.lists.items():
        check(f"{path} (exact)", before, current.lists.get(path))
    return problems
