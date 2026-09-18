import json
from pathlib import Path

import pytest

from fieldwise.documents.cord_import import map_gt_parse
from fieldwise.evals.matchers import compare_scalar, grade_document
from fieldwise.evals.runner import aggregate
from fieldwise.schemas.registry import compile_builtin

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cord"
RECEIPT = compile_builtin("receipt")


def golden(stem: str = "cord-v2_validation_0000") -> dict[str, object]:
    return map_gt_parse(json.loads((FIXTURES / f"{stem}.json").read_text()))


@pytest.mark.parametrize(
    ("matcher", "g", "p", "expected"),
    [
        ("money", 45500.0, 45500, "correct"),
        ("money", 45500.0, "45,500", "correct"),
        ("money", 45500.0, "Rp 45.500", "correct"),
        ("money", 12.5, 12.504, "correct"),
        ("money", 45500.0, 45000, "wrong"),
        ("money", None, None, "null_match"),
        ("money", 1.0, None, "missing"),
        ("money", None, 1.0, "spurious"),
        ("money", 1.0, "n/a", "wrong"),
        ("integer", 2, "2 x", "correct"),
        ("integer", 2, 3, "wrong"),
        ("text", "NASI GORENG", "nasi  goreng!", "correct"),
        ("text", "NASI GORENG", "NASI GORENK", "fuzzy"),
        ("text", "NASI GORENG", "ES TEH", "wrong"),
        ("boolean", True, True, "correct"),
        ("boolean", True, False, "wrong"),
        ("date", "2024-03-01", "2024-03-01T10:00", "correct"),
        ("date", "2024-03-01", "2024-03-02", "wrong"),
    ],
)
def test_compare_scalar(matcher: str, g: object, p: object, expected: str) -> None:
    assert compare_scalar(matcher, g, p) == expected


def test_oracle_scores_everything_correct() -> None:
    outcome = grade_document(RECEIPT, golden(), golden())
    assert outcome.all_correct
    assert set(outcome.leaves["total"]) == {"correct"}
    assert outcome.lists["line_items"].exact
    assert outcome.lists["line_items"].matched_items == 3


def test_null_baseline_scores_nothing_with_a_value() -> None:
    empty = {key: ([] if key == "line_items" else None) for key in golden()}
    outcome = grade_document(RECEIPT, golden(), empty)
    assert not outcome.all_correct
    assert outcome.leaves["total"] == ["missing"]
    assert outcome.leaves["tax"] == ["null_match"]
    assert outcome.lists["line_items"].golden_count == 3
    assert outcome.lists["line_items"].predicted_count == 0
    assert outcome.lists["line_items"].recall == 0.0
    assert outcome.lists["line_items"].precision is None


def test_plausible_but_wrong_receipt_fails() -> None:
    predicted = golden()
    predicted["total"] = 45000.0  # off by 500
    items = list(predicted["line_items"])  # type: ignore[arg-type]
    items[1] = {**items[1], "name": "EGG TARTS", "line_total": 13000.0}
    del items[2]
    predicted["line_items"] = items
    outcome = grade_document(RECEIPT, golden(), predicted)
    assert outcome.leaves["total"] == ["wrong"]
    assert outcome.leaves["line_items[].name"] == ["correct", "fuzzy", "missing"]
    assert outcome.leaves["line_items[].line_total"] == ["correct", "correct", "missing"]
    lo = outcome.lists["line_items"]
    assert (lo.golden_count, lo.predicted_count, lo.matched_items, lo.exact) == (3, 2, 1, False)


def test_extra_predicted_items_are_spurious() -> None:
    predicted = golden()
    predicted["line_items"] = [*predicted["line_items"], {"name": "GHOST", "quantity": 1}]  # type: ignore[misc]
    outcome = grade_document(RECEIPT, golden(), predicted)
    assert outcome.leaves["line_items[].name"][-1] == "spurious"
    assert outcome.lists["line_items"].precision == 0.75


def test_aggregate_computes_strict_value_and_document_metrics() -> None:
    perfect = grade_document(RECEIPT, golden(), golden())
    wrong = golden()
    wrong["total"] = 1.0
    imperfect = grade_document(RECEIPT, golden(), wrong)
    agg = aggregate(RECEIPT, [perfect, imperfect])

    assert agg.doc_exact.value == 0.5
    assert agg.per_field["total"]["n"] == 2
    assert agg.per_field["total"]["accuracy"] == 0.5
    assert agg.per_field["total"]["value_accuracy"] == 0.5
    assert agg.per_field["tax"]["accuracy"] == 1.0  # null in both
    assert agg.per_field["tax"]["value_n"] == 0
    assert agg.per_field["tax"]["value_accuracy"] is None
    assert agg.lists["line_items"]["exact_rate"] == 1.0
    assert agg.lists["line_items"]["item_recall"] == 1.0
    assert agg.overall.value is not None
    assert agg.value.value is not None
    assert agg.value.value < agg.overall.value  # null matches inflate the strict number
    low, high = agg.per_field["total"]["ci"]
    assert 0.0 <= low < 0.5 < high <= 1.0
