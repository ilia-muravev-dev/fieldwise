import json
from pathlib import Path

from fieldwise.documents.cord_import import map_gt_parse
from fieldwise.extraction.builder import with_evidence
from fieldwise.extraction.pipeline import inconsistency, split_evidence
from fieldwise.extraction.prompts.registry import get_prompt
from fieldwise.schemas.registry import compile_builtin

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cord"


def golden() -> dict[str, object]:
    return map_gt_parse(json.loads((FIXTURES / "cord-v2_validation_0000.json").read_text()))


def test_evidence_schema_wraps_the_values_and_lists_top_level_amounts() -> None:
    wrapped = with_evidence(compile_builtin("receipt"))
    assert wrapped["required"] == ["fields", "evidence"]
    assert wrapped["properties"]["fields"] == compile_builtin("receipt").strict
    evidence = wrapped["properties"]["evidence"]
    assert evidence["required"] == [
        "subtotal",
        "discount",
        "service_charge",
        "tax",
        "total",
        "cash_paid",
        "change",
        "card_paid",
        "item_count",
    ]
    assert evidence["additionalProperties"] is False


def test_split_evidence() -> None:
    fields, evidence = split_evidence(
        {"fields": {"total": 1}, "evidence": {"total": "TOTAL 1", "tax": ""}}
    )
    assert fields == {"total": 1}
    assert evidence == {"total": "TOTAL 1"}
    assert split_evidence({"total": 1}) == ({"total": 1}, None)


def test_inconsistency_detects_sums_that_do_not_add_up() -> None:
    consistent = golden()  # 16500 + 13000 + 16000 = 45500 = total, no subtotal
    assert inconsistency(consistent) is None

    off = golden()
    off["total"] = 55500.0
    assert inconsistency(off) == "the line totals add up to 45500.0 but the total is 55500.0"

    with_subtotal = golden()
    with_subtotal["subtotal"] = 45500.0
    with_subtotal["tax"] = 4550.0
    with_subtotal["total"] = 50050.0
    assert inconsistency(with_subtotal) is None  # items reach the subtotal; tax explains the total

    taxed_without_subtotal = golden()
    taxed_without_subtotal["tax"] = 4550.0
    taxed_without_subtotal["total"] = 50050.0
    assert inconsistency(taxed_without_subtotal) is None  # nothing to reconcile against

    missing_line_total = golden()
    missing_line_total["line_items"][0]["line_total"] = None  # type: ignore[index]
    assert inconsistency(missing_line_total) is None

    small_rounding = golden()
    small_rounding["total"] = 45500.9
    assert inconsistency(small_rounding) is None
    assert inconsistency({"line_items": [], "total": 1.0}) is None


def test_v4_spec_switches_everything_on() -> None:
    spec = get_prompt("v4")
    assert (spec.use_ocr_text, spec.fewshot_k, spec.use_evidence, spec.consistency_check) == (
        True,
        3,
        True,
        True,
    )
    rendered = spec.render_system({"title": "receipt", "type": "object", "properties": {}})
    assert "evidence" in rendered
    assert "add up" in rendered
