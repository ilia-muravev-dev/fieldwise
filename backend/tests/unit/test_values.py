from decimal import Decimal

import pytest

from fieldwise.values import normalise_text, parse_int, parse_money


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("60.000", Decimal("60000")),
        ("60,000", Decimal("60000")),
        ("1.234.567", Decimal("1234567")),
        ("12,50", Decimal("12.50")),
        ("12.5", Decimal("12.5")),
        ("1.234,50", Decimal("1234.50")),
        ("1,234.50", Decimal("1234.50")),
        ("Rp 60.000", Decimal("60000")),
        ("IDR60.000,-", Decimal("60000")),
        ("-60.000", Decimal("-60000")),
        ("(60.000)", Decimal("-60000")),
        ("@ 15.000", Decimal("15000")),
        ("60000", Decimal("60000")),
        (60000, Decimal("60000")),
        (12.5, Decimal("12.5")),
        (["", "60.000"], Decimal("60000")),
    ],
)
def test_parse_money(raw: object, expected: Decimal) -> None:
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "free", "-", "()", [], True])
def test_parse_money_rejects_non_amounts(raw: object) -> None:
    assert parse_money(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2", 2), ("2 x", 2), ("x2", 2), ("2.00", 2), (3, 3), (2.9, 2), (["", "4"], 4), ("qty", None)],
)
def test_parse_int(raw: object, expected: int | None) -> None:
    assert parse_int(raw) == expected


def test_normalise_text_folds_case_whitespace_and_punctuation() -> None:
    assert normalise_text("  NASI  Goreng, (Spicy)!! ") == "nasi goreng spicy"
    assert normalise_text(["Es", "Teh"]) == "es teh"
    assert normalise_text(None) == ""
