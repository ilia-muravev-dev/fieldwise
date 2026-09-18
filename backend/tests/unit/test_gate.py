import json

from fieldwise.extraction.builder import with_evidence
from fieldwise.extraction.factory import empty_answer
from fieldwise.extraction.pipeline import parse_output
from fieldwise.extraction.provider import LLMRequest
from fieldwise.gate.bundle import GateBaseline, compare_to_baseline
from fieldwise.schemas.registry import compile_builtin


def baseline(**overrides: object) -> GateBaseline:
    base = {
        "prompt": "v2",
        "model": "m",
        "overall_accuracy": 0.91,
        "value_accuracy": 0.95,
        "doc_exact_rate": 0.5,
        "per_field": {"total": 0.94, "tax": 1.0},
        "lists": {"line_items": 0.67},
    }
    base.update(overrides)
    return GateBaseline.from_dict(base)


def test_no_regression_within_tolerance() -> None:
    current = baseline(overall_accuracy=0.90, per_field={"total": 0.93, "tax": 1.0})
    assert compare_to_baseline(current, baseline(), tolerance=0.02) == []


def test_regressions_are_named() -> None:
    current = baseline(
        value_accuracy=0.90, per_field={"total": 0.80, "tax": 1.0}, lists={"line_items": 0.5}
    )
    problems = compare_to_baseline(current, baseline(), tolerance=0.02)
    assert problems == [
        "value_accuracy: 95.0% → 90.0%",
        "total: 94.0% → 80.0%",
        "line_items (exact): 67.0% → 50.0%",
    ]


def test_missing_numbers_are_skipped_and_round_trip() -> None:
    current = baseline(per_field={"tax": 1.0}, overall_accuracy=None)
    assert compare_to_baseline(current, baseline(), tolerance=0.02) == []
    assert GateBaseline.from_dict(baseline().to_dict()) == baseline()


def test_fake_answer_is_valid_for_every_prompt() -> None:
    compiled = compile_builtin("receipt")
    for schema in (compiled.strict, with_evidence(compiled)):
        request = LLMRequest(model="m", system="", content=[], output_schema=schema)
        parse_output(json.dumps(empty_answer(request)), schema)
