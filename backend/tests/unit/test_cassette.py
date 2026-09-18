from pathlib import Path

import pytest

from fieldwise.extraction.cassette import CassetteProvider, cassette_key
from fieldwise.extraction.provider import FakeProvider, LLMError, LLMRequest

SCHEMA = {"type": "object", "properties": {}, "required": []}


def request(document: str = "doc-a", effort: str = "low") -> LLMRequest:
    return LLMRequest(
        model="claude-sonnet-5",
        system="sys",
        content=[{"type": "text", "text": "x"}],
        output_schema=SCHEMA,
        effort=effort,
        cache_key={"document": document, "prompt": "v1"},
    )


def test_key_depends_on_identity_not_on_content_bytes() -> None:
    a = cassette_key("anthropic", request())
    same_with_other_content = request()
    object.__setattr__(same_with_other_content, "content", [{"type": "text", "text": "y"}])
    assert cassette_key("anthropic", same_with_other_content) == a
    assert cassette_key("anthropic", request(document="doc-b")) != a
    assert cassette_key("anthropic", request(effort="high")) != a
    assert cassette_key("fake", request()) != a


def test_record_then_replay(tmp_path: Path) -> None:
    inner = FakeProvider(lambda req: {"n": len(inner.requests)})
    recorder = CassetteProvider(inner, tmp_path, "record")

    first = recorder.complete(request())
    second = recorder.complete(request())  # already recorded → no inner call
    assert first.text == second.text == '{"n": 1}'
    assert len(inner.requests) == 1
    assert (recorder.hits, recorder.misses) == (1, 1)
    assert len(list(tmp_path.glob("*.json"))) == 1

    replayer = CassetteProvider(FakeProvider(lambda req: {"never": True}), tmp_path, "replay")
    assert replayer.complete(request()).text == '{"n": 1}'
    with pytest.raises(LLMError) as info:
        replayer.complete(request(document="doc-b"))
    assert info.value.kind == "cassette_miss"


def test_off_mode_is_a_passthrough(tmp_path: Path) -> None:
    inner = FakeProvider(lambda req: {"ok": True})
    provider = CassetteProvider(inner, tmp_path, "off")
    provider.complete(request())
    provider.complete(request())
    assert len(inner.requests) == 2
    assert not list(tmp_path.glob("*.json"))
