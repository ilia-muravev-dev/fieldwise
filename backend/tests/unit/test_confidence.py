from fieldwise.documents.ocr import OcrSpan, OcrWord
from fieldwise.extraction.confidence import flatten, score_fields, value_variants


def span(text: str, box: tuple[int, int, int, int], words: list[str] | None = None) -> OcrSpan:
    word_boxes = ()
    if words:
        step = (box[2] - box[0]) // len(words)
        word_boxes = tuple(
            OcrWord(w, (box[0] + i * step, box[1], box[0] + (i + 1) * step, box[3]), 0.9)
            for i, w in enumerate(words)
        )
    return OcrSpan(text=text, box=box, conf=0.99, words=word_boxes)


SPANS = [
    span("1 REAL GANACHE", (119, 382, 260, 409), ["1", "REAL", "GANACHE"]),
    span("16,500", (398, 379, 463, 408), ["16,500"]),
    span("TOTAL", (137, 474, 242, 521)),
    span("45,500", (341, 470, 466, 519), ["45,500"]),
]


def test_flatten_gives_concrete_paths() -> None:
    assert flatten({"a": 1, "items": [{"n": "x"}, {"n": None}], "b": {"c": 2}}) == [
        ("a", 1),
        ("items[0].n", "x"),
        ("items[1].n", None),
        ("b.c", 2),
    ]


def test_value_variants_cover_printed_number_formats() -> None:
    assert {"45500", "45,500", "45.500", "45500.00"} <= set(value_variants(45500))
    assert "12,50" in value_variants(12.5)
    assert value_variants(" Nasi  Goreng ") == ["Nasi Goreng"]
    assert value_variants(True) == ["true"]
    assert {"5,000", "5.000", "5000"} <= set(value_variants(-5000))


def test_score_fields_grounds_values_in_spans() -> None:
    result = {
        "line_items": [{"name": "REAL GANACHE", "quantity": 1, "line_total": 16500.0}],
        "total": 45500.0,
        "tax": None,
        "change": 999.0,
    }
    confidences, boxes = score_fields(result, SPANS)

    assert confidences["total"] == 1.0
    assert boxes["total"] == [(341, 470, 466, 519)]
    assert confidences["line_items[0].name"] == 1.0
    assert boxes["line_items[0].name"] == [(166, 382, 213, 409), (213, 382, 260, 409)]
    assert confidences["line_items[0].line_total"] == 1.0
    assert boxes["line_items[0].line_total"] == [(398, 379, 463, 408)]
    assert "tax" not in confidences
    assert confidences["change"] < 0.8
    assert "change" not in boxes


def test_score_fields_without_spans() -> None:
    confidences, boxes = score_fields({"total": 1.0}, [])
    assert confidences == {"total": 0.0}
    assert boxes == {}
