"""Grading one extraction against its golden label, field by field.

Outcomes per leaf:
- correct     both present and equal under the field's matcher
- null_match  both null — counted as correct in the strict accuracy, excluded from value accuracy
- fuzzy     text only: not equal after normalisation but similar (ratio ≥ 90) — reported
            separately and counted as *wrong* in the strict accuracy
- wrong     both present, different
- missing   golden has a value, the prediction is null
- spurious  golden is null, the prediction has a value

Lists are aligned by position (receipt items are ordered); item fields are graded like leaves and
the list itself gets an exact-match flag plus item-level precision/recall."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from rapidfuzz import fuzz

from fieldwise.schemas.compiler import CompiledSchema, FieldMeta
from fieldwise.values import normalise_text, parse_int, parse_money

Outcome = Literal["correct", "null_match", "fuzzy", "wrong", "missing", "spurious"]
CORRECT_OUTCOMES = {"correct", "null_match"}
MONEY_TOLERANCE = Decimal("0.005")
FUZZY_THRESHOLD = 90.0


def _is_null(value: Any) -> bool:
    return value is None or value == ""


def compare_scalar(matcher: str, golden: Any, predicted: Any) -> Outcome:
    if _is_null(golden) and _is_null(predicted):
        return "null_match"
    if _is_null(golden):
        return "spurious"
    if _is_null(predicted):
        return "missing"
    if matcher == "text":
        return _compare_text(golden, predicted)
    return "correct" if _values_equal(matcher, golden, predicted) else "wrong"


def _values_equal(matcher: str, golden: Any, predicted: Any) -> bool:
    if matcher in {"money", "number"}:
        g, p = parse_money(golden), parse_money(predicted)
        return g is not None and p is not None and abs(g - p) <= MONEY_TOLERANCE
    if matcher == "integer":
        return parse_int(golden) == parse_int(predicted)
    if matcher == "boolean":
        return bool(golden) == bool(predicted)
    if matcher == "date":
        return _as_date(golden) == _as_date(predicted)
    return normalise_text(golden) == normalise_text(predicted)


def _compare_text(golden: Any, predicted: Any) -> Outcome:
    g_text, p_text = normalise_text(golden), normalise_text(predicted)
    if g_text == p_text:
        return "correct"
    return "fuzzy" if fuzz.ratio(g_text, p_text) >= FUZZY_THRESHOLD else "wrong"


def _as_date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value).strip()[:10]).isoformat()
    except ValueError:
        return normalise_text(value)


@dataclass
class ListOutcome:
    path: str
    golden_count: int
    predicted_count: int
    matched_items: int  # aligned items with every field correct
    exact: bool

    @property
    def precision(self) -> float | None:
        return self.matched_items / self.predicted_count if self.predicted_count else None

    @property
    def recall(self) -> float | None:
        return self.matched_items / self.golden_count if self.golden_count else None


@dataclass
class DocumentOutcome:
    """Outcomes keyed by schema path (`line_items[].name` for item fields, possibly repeated)."""

    leaves: dict[str, list[Outcome]] = field(default_factory=dict)
    lists: dict[str, ListOutcome] = field(default_factory=dict)

    def add(self, path: str, outcome: Outcome) -> None:
        self.leaves.setdefault(path, []).append(outcome)

    @property
    def all_correct(self) -> bool:
        leaves_ok = all(
            o in CORRECT_OUTCOMES for outcomes in self.leaves.values() for o in outcomes
        )
        return leaves_ok and all(lo.exact for lo in self.lists.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "leaves": self.leaves,
            "lists": {
                path: {
                    "golden_count": lo.golden_count,
                    "predicted_count": lo.predicted_count,
                    "matched_items": lo.matched_items,
                    "exact": lo.exact,
                }
                for path, lo in self.lists.items()
            },
            "all_correct": self.all_correct,
        }


def grade_document(
    compiled: CompiledSchema, golden: dict[str, Any], predicted: dict[str, Any]
) -> DocumentOutcome:
    outcome = DocumentOutcome()
    by_path = {f.path: f for f in compiled.fields}
    for meta in compiled.fields:
        if "[]" in meta.path or meta.matcher == "object":
            continue  # item fields are graded through their list; objects through their leaves
        if meta.matcher == "list":
            _grade_list(meta, by_path, _get(golden, meta.path), _get(predicted, meta.path), outcome)
        else:
            outcome.add(
                meta.path,
                compare_scalar(meta.matcher, _get(golden, meta.path), _get(predicted, meta.path)),
            )
    return outcome


def _grade_list(
    meta: FieldMeta,
    by_path: dict[str, FieldMeta],
    golden_items: Any,
    predicted_items: Any,
    outcome: DocumentOutcome,
) -> None:
    golden_list = golden_items if isinstance(golden_items, list) else []
    predicted_list = predicted_items if isinstance(predicted_items, list) else []
    children = [by_path[child] for child in meta.children]
    matched = 0
    for index in range(max(len(golden_list), len(predicted_list))):
        g_item = golden_list[index] if index < len(golden_list) else None
        p_item = predicted_list[index] if index < len(predicted_list) else None
        item_correct = g_item is not None and p_item is not None
        for child in children:
            key = child.path.rsplit(".", 1)[-1]
            g_value = g_item.get(key) if isinstance(g_item, dict) else None
            p_value = p_item.get(key) if isinstance(p_item, dict) else None
            if g_item is None and p_item is None:
                continue
            child_outcome: Outcome
            if g_item is None:
                child_outcome = "spurious"
            elif p_item is None:
                child_outcome = "missing"
            else:
                child_outcome = compare_scalar(child.matcher, g_value, p_value)
            outcome.add(child.path, child_outcome)
            item_correct = item_correct and child_outcome in CORRECT_OUTCOMES
        if not children and g_item is not None and p_item is not None:
            item_correct = compare_scalar("text", g_item, p_item) in CORRECT_OUTCOMES
        matched += int(item_correct)
    outcome.lists[meta.path] = ListOutcome(
        path=meta.path,
        golden_count=len(golden_list),
        predicted_count=len(predicted_list),
        matched_items=matched,
        exact=len(golden_list) == len(predicted_list) == matched,
    )


def _get(data: Any, path: str) -> Any:
    """Dotted path lookup on nested dicts (no list indexing — lists are graded as wholes)."""
    current = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current
