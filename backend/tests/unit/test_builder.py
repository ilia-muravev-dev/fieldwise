import base64
import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from fieldwise.extraction.builder import FewShotExample, build_request
from fieldwise.extraction.prompts.registry import PROMPTS, get_prompt
from fieldwise.schemas.registry import compile_builtin, load_builtin

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cord"


def _jpeg(size: tuple[int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def build(**overrides: object) -> object:
    kwargs: dict[str, object] = {
        "spec": get_prompt("v1"),
        "compiled": compile_builtin("receipt"),
        "authored_schema": load_builtin("receipt"),
        "page_jpegs": [_jpeg((400, 600))],
        "ocr_text": "TOTAL 45,500",
        "examples": [],
        "model": "claude-sonnet-5",
        "effort": "low",
        "max_tokens": 4096,
        "cache_key": {"document": "sha"},
    }
    kwargs.update(overrides)
    return build_request(**kwargs)  # type: ignore[arg-type]


def test_v1_sends_the_schema_in_the_system_prompt_and_the_image_only() -> None:
    request = build()
    assert request.system.startswith("You extract structured data")
    assert '"title": "receipt"' in request.system
    assert "$schema_json" not in request.system
    types = [block["type"] for block in request.content]
    assert types == ["image", "text"]
    assert request.content[-1]["text"].startswith("Extract the fields")
    assert request.output_schema == compile_builtin("receipt").strict
    assert request.cache_key == {"document": "sha", "prompt": "v1", "fewshot": ""}


def test_ocr_text_and_examples_are_added_when_the_spec_asks() -> None:
    spec = get_prompt("v1")
    with_text = type(spec)(name="v1", notes="", use_ocr_text=True)
    example = FewShotExample("doc-1", "TOTAL 10,000", {"total": 10000})
    request = build(spec=with_text, examples=[example])
    types = [block["type"] for block in request.content]
    assert types == ["text", "text", "image", "text"]
    assert "Example 1 — OCR text" in request.content[0]["text"]
    assert json.dumps({"total": 10000}) in request.content[0]["text"]
    assert "TOTAL 45,500" in request.content[1]["text"]
    assert request.cache_key["fewshot"] == "doc-1"


def test_images_are_downscaled_for_the_model() -> None:
    request = build(page_jpegs=[_jpeg((3000, 4000)), _jpeg((100, 100))])
    images = [block for block in request.content if block["type"] == "image"]
    assert len(images) == 2
    with Image.open(BytesIO(base64.b64decode(images[0]["source"]["data"]))) as image:
        assert max(image.size) == 1568
    assert images[0]["source"]["media_type"] == "image/jpeg"


def test_system_prompt_is_stable_across_documents() -> None:
    assert build().system == build(cache_key={"document": "other"}).system


def test_every_registered_prompt_renders() -> None:
    for name in PROMPTS:
        rendered = get_prompt(name).render_system(load_builtin("receipt"))
        assert "Schema" in rendered
