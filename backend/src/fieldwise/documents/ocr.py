"""OCR behind a small protocol. RapidOCR (PP-OCR models on ONNX Runtime, pip-only, no system
packages) is the real provider; a fake one serves the tests and the e2e profile.

Boxes are axis-aligned `(x0, y0, x1, y1)` in the pixel space of the stored page image, so the
review UI can draw them over the same image without any rescaling on the server."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class OcrWord:
    text: str
    box: Box
    conf: float


@dataclass(frozen=True)
class OcrSpan:
    """One detected text line (RapidOCR's unit of detection) with its word boxes."""

    text: str
    box: Box
    conf: float
    words: tuple[OcrWord, ...] = ()

    @property
    def center_y(self) -> float:
        return (self.box[1] + self.box[3]) / 2

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


class OcrProvider(Protocol):
    def recognise(self, jpeg: bytes) -> list[OcrSpan]: ...


def quad_to_box(quad: Any) -> Box:
    points = np.asarray(quad, dtype=float).reshape(-1, 2)
    x0, y0 = points.min(axis=0)
    x1, y1 = points.max(axis=0)
    return (round(float(x0)), round(float(y0)), round(float(x1)), round(float(y1)))


class RapidOcrProvider:
    """Lazy: the ONNX sessions are created on first use, once per process."""

    def __init__(self) -> None:
        self._engine: Any = None

    def _get_engine(self) -> Any:
        if self._engine is None:
            from rapidocr import RapidOCR  # noqa: PLC0415 — heavy import, only when OCR runs

            self._engine = RapidOCR()
        return self._engine

    def recognise(self, jpeg: bytes) -> list[OcrSpan]:
        import cv2  # noqa: PLC0415 — heavy import, only when OCR runs

        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("could not decode the page image")
        output = self._get_engine()(image, return_word_box=True)
        if output.boxes is None or output.txts is None:
            return []
        word_results = output.word_results or ()
        spans: list[OcrSpan] = []
        for index, (quad, text, score) in enumerate(
            zip(output.boxes, output.txts, output.scores, strict=True)
        ):
            words = tuple(
                OcrWord(text=str(w_text), box=quad_to_box(w_quad), conf=float(w_conf))
                for w_text, w_conf, w_quad in (
                    word_results[index] if index < len(word_results) else ()
                )
            )
            spans.append(
                OcrSpan(text=str(text), box=quad_to_box(quad), conf=float(score), words=words)
            )
        return spans


class FakeOcrProvider:
    def __init__(self, spans: list[OcrSpan] | None = None) -> None:
        self.spans = spans or []
        self.calls = 0

    def recognise(self, jpeg: bytes) -> list[OcrSpan]:
        self.calls += 1
        return list(self.spans)


def reading_order(spans: list[OcrSpan]) -> list[list[OcrSpan]]:
    """Groups spans into visual lines (top to bottom), each ordered left to right.

    Two spans share a line when their vertical centres are closer than 60% of the median
    span height — receipts are printed on a grid, so this is robust without any ML."""
    if not spans:
        return []
    tolerance = 0.6 * statistics.median(max(s.height, 1) for s in spans)
    lines: list[list[OcrSpan]] = []
    for span in sorted(spans, key=lambda s: (s.center_y, s.box[0])):
        if lines and abs(span.center_y - _line_center(lines[-1])) <= tolerance:
            lines[-1].append(span)
        else:
            lines.append([span])
    return [sorted(line, key=lambda s: s.box[0]) for line in lines]


def _line_center(line: list[OcrSpan]) -> float:
    return sum(s.center_y for s in line) / len(line)


def spans_to_text(spans: list[OcrSpan]) -> str:
    """Plain text in reading order; spans on one visual line are separated by two spaces so a
    price stays on the same line as its item ("1 EGG TART  13,000")."""
    return "\n".join("  ".join(s.text for s in line) for line in reading_order(spans))


def serialise_spans(spans: list[OcrSpan], page: int) -> list[dict[str, Any]]:
    return [
        {
            "page": page,
            "text": s.text,
            "box": list(s.box),
            "conf": round(s.conf, 4),
            "words": [
                {"text": w.text, "box": list(w.box), "conf": round(w.conf, 4)} for w in s.words
            ],
        }
        for s in spans
    ]


def _box(values: list[Any]) -> Box:
    x0, y0, x1, y1 = (int(v) for v in values)
    return (x0, y0, x1, y1)


def deserialise_spans(records: list[dict[str, Any]]) -> list[OcrSpan]:
    return [
        OcrSpan(
            text=str(r["text"]),
            box=_box(r["box"]),
            conf=float(r["conf"]),
            words=tuple(
                OcrWord(text=str(w["text"]), box=_box(w["box"]), conf=float(w["conf"]))
                for w in r.get("words", [])
            ),
        )
        for r in records
    ]
