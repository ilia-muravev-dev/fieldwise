from pathlib import Path

from fieldwise.documents.ocr import (
    FakeOcrProvider,
    OcrSpan,
    OcrWord,
    RapidOcrProvider,
    deserialise_spans,
    quad_to_box,
    reading_order,
    serialise_spans,
    spans_to_text,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cord"


def span(text: str, *box: int) -> OcrSpan:
    x0, y0, x1, y1 = box
    return OcrSpan(text=text, box=(x0, y0, x1, y1), conf=0.99)


def test_quad_to_box_is_the_axis_aligned_bounding_box() -> None:
    assert quad_to_box([[118, 405], [224, 404], [224, 431], [119, 433]]) == (118, 404, 224, 433)


def test_reading_order_groups_lines_and_sorts_left_to_right() -> None:
    spans = [
        span("16,500", 398, 379, 463, 408),
        span("13,000", 399, 403, 463, 429),
        span("1 EGG TART", 118, 405, 224, 431),
        span("1 REAL GANACHE", 119, 382, 260, 409),
        span("TOTAL", 137, 474, 242, 521),
        span("45,500", 341, 470, 466, 519),
    ]
    lines = reading_order(spans)
    assert [[s.text for s in line] for line in lines] == [
        ["1 REAL GANACHE", "16,500"],
        ["1 EGG TART", "13,000"],
        ["TOTAL", "45,500"],
    ]
    assert spans_to_text(spans) == "1 REAL GANACHE  16,500\n1 EGG TART  13,000\nTOTAL  45,500"


def test_reading_order_of_nothing() -> None:
    assert reading_order([]) == []
    assert spans_to_text([]) == ""


def test_serialise_round_trip() -> None:
    spans = [
        OcrSpan(
            text="1 EGG TART",
            box=(118, 404, 224, 433),
            conf=0.98321,
            words=(
                OcrWord("1", (118, 404, 128, 433), 0.9),
                OcrWord("EGG", (135, 404, 170, 433), 0.97),
            ),
        )
    ]
    records = serialise_spans(spans, page=1)
    assert records[0]["page"] == 1
    assert records[0]["conf"] == 0.9832
    assert records[0]["words"][1] == {"text": "EGG", "box": [135, 404, 170, 433], "conf": 0.97}
    restored = deserialise_spans(records)
    assert restored[0].text == "1 EGG TART"
    assert restored[0].box == (118, 404, 224, 433)
    assert restored[0].words[0].text == "1"


def test_fake_provider_counts_calls() -> None:
    provider = FakeOcrProvider([span("TOTAL", 0, 0, 10, 10)])
    assert provider.recognise(b"jpeg") == [span("TOTAL", 0, 0, 10, 10)]
    assert provider.calls == 1


def test_rapidocr_reads_a_real_receipt() -> None:
    jpeg = (FIXTURES / "cord-v2_validation_0000.jpg").read_bytes()
    spans = RapidOcrProvider().recognise(jpeg)
    text = spans_to_text(spans)
    assert "REAL GANACHE" in text
    assert "45,500" in text
    assert all(0 <= s.box[0] < s.box[2] <= 600 and 0 <= s.box[1] < s.box[3] <= 900 for s in spans)
    assert any(len(s.words) > 1 for s in spans)
    assert all(0 <= s.conf <= 1 for s in spans)
