"""Parsing and normalisation of printed values. Shared by the dataset importer (to normalise
ground truth once) and the eval matchers (to normalise predictions the same way)."""

import re
from decimal import Decimal, InvalidOperation

_MONEY_JUNK = re.compile(r"[^\d,.\-()]")
_INT_IN_TEXT = re.compile(r"\d+")


def parse_money(raw: object) -> Decimal | None:
    """Turns printed amounts into a Decimal, or None when nothing numeric is there.

    Handles currency symbols and words, thousands separators in either style ("60.000" and
    "60,000" are both sixty thousand), decimal separators in either style ("12,50" and "12.50"),
    negatives written as "-1.000" or "(1.000)", and lists (first parseable element wins).
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int | float | Decimal):
        return Decimal(str(raw))
    if isinstance(raw, list | tuple):
        return next((m for m in (parse_money(item) for item in raw) if m is not None), None)
    return _parse_money_text(str(raw))


def _parse_money_text(raw: str) -> Decimal | None:
    text = _MONEY_JUNK.sub("", raw)
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    digits = text.strip("-()")
    if not any(ch.isdigit() for ch in digits):
        return None
    try:
        value = Decimal(_normalise_separators(digits))
    except InvalidOperation:
        return None
    return -value if negative else value


def _normalise_separators(digits: str) -> str:
    has_dot, has_comma = "." in digits, "," in digits
    if has_dot and has_comma:
        # The last separator is the decimal one; everything else groups thousands.
        last = max(digits.rfind("."), digits.rfind(","))
        integer_part = re.sub(r"[.,]", "", digits[:last])
        return f"{integer_part}.{digits[last + 1 :]}"
    separator = "." if has_dot else "," if has_comma else None
    if separator is None:
        return digits
    head, *groups = digits.split(separator)
    if groups and all(len(g) == 3 for g in groups):
        return head + "".join(groups)  # 60.000 or 1.234.567 → thousands
    if len(groups) == 1 and len(groups[0]) in (1, 2):
        return f"{head}.{groups[0]}"  # 12,5 or 12.50 → decimals
    return head + "".join(groups)


def parse_int(raw: object) -> int | None:
    """First integer in the text: "2 x" → 2, "x2" → 2, "2.00" → 2, 3 → 3."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float | Decimal):
        return int(raw)
    if isinstance(raw, list | tuple):
        for item in raw:
            parsed = parse_int(item)
            if parsed is not None:
                return parsed
        return None
    match = _INT_IN_TEXT.search(str(raw))
    return int(match.group()) if match else None


def normalise_text(raw: object) -> str:
    """Case-folded, whitespace-collapsed, punctuation-light text for comparisons."""
    if raw is None:
        return ""
    if isinstance(raw, list | tuple):
        raw = " ".join(str(item) for item in raw)
    text = str(raw).casefold()
    text = re.sub(r"[^\w\s%&+/@-]", " ", text)
    return " ".join(text.split())
