"""Grounds extracted values in the OCR output: a value that can be found (fuzzily) in a detected
text span gets a confidence close to 1 and the span's box; a value the OCR never saw gets a low
score, which the review UI surfaces first."""

import re
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz

from fieldwise.documents.ocr import Box, OcrSpan

MATCH_THRESHOLD = 80.0


def flatten(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Leaf paths with concrete indices: line_items[0].name, total, ..."""
    if isinstance(value, dict):
        out: list[tuple[str, Any]] = []
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.extend(flatten(child, path))
        return out
    if isinstance(value, list):
        out = []
        for index, child in enumerate(value):
            out.extend(flatten(child, f"{prefix}[{index}]"))
        return out
    return [(prefix, value)]


def value_variants(value: Any) -> list[str]:
    """The ways a value may have been printed: 45500 → 45500, 45,500, 45.500, 45500.00 ..."""
    if isinstance(value, bool):
        return [str(value).lower()]
    if isinstance(value, int | float | Decimal):
        number = Decimal(str(value))
        integral = number == number.to_integral_value()
        magnitude = abs(number)
        variants = {str(magnitude), f"{magnitude:,}", f"{magnitude:,}".replace(",", ".")}
        if integral:
            whole = int(magnitude)
            variants |= {
                str(whole),
                f"{whole:,}",
                f"{whole:,}".replace(",", "."),
                f"{whole}.00",
                f"{whole:,}.00",
            }
        else:
            variants.add(f"{magnitude:.2f}".replace(".", ","))
        return sorted(variants, key=len, reverse=True)
    text = " ".join(str(value).split())
    return [text] if text else []


def score_fields(
    result: dict[str, Any], spans: list[OcrSpan]
) -> tuple[dict[str, float], dict[str, list[Box]]]:
    confidences: dict[str, float] = {}
    boxes: dict[str, list[Box]] = {}
    span_texts = [(span, span.text.lower()) for span in spans]
    for path, value in flatten(result):
        if value is None or value == "":
            continue
        variants = [v.lower() for v in value_variants(value)]
        best_score, best_span = 0.0, None
        for span, lowered in span_texts:
            score = max((fuzz.partial_ratio(variant, lowered) for variant in variants), default=0.0)
            if score > best_score:
                best_score, best_span = score, span
        confidences[path] = round(best_score / 100, 3)
        if best_span is not None and best_score >= MATCH_THRESHOLD:
            boxes[path] = _word_boxes(best_span, variants) or [best_span.box]
    return confidences, boxes


def _word_boxes(span: OcrSpan, variants: list[str]) -> list[Box]:
    """Tighter than the span: the words that make up the value (e.g. the price, not the item)."""
    tokens = {t for variant in variants for t in re.split(r"\s+", variant) if t}
    matched = [
        word.box
        for word in span.words
        if any(fuzz.ratio(word.text.lower(), token) >= 90 for token in tokens)
    ]
    return matched
