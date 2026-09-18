# ADR 0002: RapidOCR (PP-OCR on ONNX Runtime) instead of Tesseract

Status: accepted · 2026-09-18

## Context

The pipeline needs OCR for three things: text for the model alongside the image, text to embed for
few-shot retrieval, and word boxes so the review UI can highlight where a value came from.
The receipts are phone photos — skewed, shadowed, low contrast — which is where Tesseract, built for
scanned print, is weakest. Tesseract is also a system package (`apt`/`brew`), which complicates the
Docker image and every contributor's setup.

## Decision

Use `rapidocr` (PaddleOCR's PP-OCR models exported to ONNX, run by `onnxruntime`): a pure-pip
dependency with the models inside the wheel, word-level boxes via `return_word_box`, and ~0.3 s per
receipt on a laptop CPU. OpenCV is pinned to the headless build through a uv dependency override so
the container carries no GUI libraries. The provider sits behind `OcrProvider`, so Tesseract or a
cloud OCR can be swapped in for a comparison later.

## Consequences

- No system dependencies; the same `uv sync` works on macOS, CI and in the image.
- Small glyphs (a lone "1" for a quantity) are sometimes missed on full-resolution pages. The model
  also receives the image, and the v2 → v4 evals report what the OCR text contributes on top of it.
- Reading order is reconstructed by grouping boxes into visual lines (60% of the median height),
  which keeps an item and its price on one line for the prompt.
