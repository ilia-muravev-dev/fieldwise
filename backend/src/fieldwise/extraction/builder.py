"""Builds the model request for one document: the system prompt (stable across documents, so it
is the cached prefix), then per-document content — few-shot examples, OCR text, page images."""

import base64
import json
from dataclasses import dataclass
from typing import Any

from fieldwise.documents.render import downscale_jpeg
from fieldwise.extraction.prompts.registry import PromptSpec
from fieldwise.extraction.provider import LLMRequest
from fieldwise.schemas.compiler import CompiledSchema

MODEL_IMAGE_MAX_EDGE = 1568  # the largest edge the vision encoder uses without downscaling


@dataclass(frozen=True)
class FewShotExample:
    document_id: str
    ocr_text: str
    output: dict[str, Any]


def build_request(
    *,
    spec: PromptSpec,
    compiled: CompiledSchema,
    authored_schema: dict[str, Any],
    page_jpegs: list[bytes],
    ocr_text: str | None,
    examples: list[FewShotExample],
    model: str,
    effort: str,
    max_tokens: int,
    cache_key: dict[str, str],
) -> LLMRequest:
    content: list[dict[str, Any]] = []
    for index, example in enumerate(examples, start=1):
        content.append(
            {
                "type": "text",
                "text": (
                    f"Example {index} — OCR text of a similar document:\n{example.ocr_text}\n\n"
                    f"Example {index} — correct output:\n"
                    f"{json.dumps(example.output, ensure_ascii=False)}"
                ),
            }
        )
    if spec.use_ocr_text and ocr_text:
        content.append(
            {
                "type": "text",
                "text": (
                    "OCR text of the document in reading order (it may contain errors; "
                    f"the image is authoritative):\n{ocr_text}"
                ),
            }
        )
    for jpeg in page_jpegs:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(
                        downscale_jpeg(jpeg, MODEL_IMAGE_MAX_EDGE)
                    ).decode("ascii"),
                },
            }
        )
    content.append(
        {
            "type": "text",
            "text": "Extract the fields defined by the schema from this document. Respond with the "
            "JSON object only.",
        }
    )
    return LLMRequest(
        model=model,
        system=spec.render_system(authored_schema),
        content=content,
        output_schema=compiled.strict,
        effort=effort,
        max_tokens=max_tokens,
        cache_key={
            **cache_key,
            "prompt": spec.name,
            "fewshot": ",".join(e.document_id for e in examples),
        },
    )
