import json
from types import SimpleNamespace
from typing import Any

import httpx2 as httpx
import openai
import pytest

from fieldwise.extraction.openai_compat import (
    OpenAICompatibleProvider,
    provider_name_for,
    to_openai_content,
)
from fieldwise.extraction.provider import LLMError, LLMRequest

SCHEMA = {"type": "object", "properties": {"total": {"type": "number"}}, "required": ["total"]}


def request(model: str = "qwen/qwen3.8-27b:free") -> LLMRequest:
    return LLMRequest(
        model=model,
        system="You extract.",
        content=[
            {"type": "text", "text": "Extract."},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAA="},
            },
        ],
        output_schema=SCHEMA,
        cache_key={"document": "abc"},
    )


class StubCompletions:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def stub_client(*responses: Any) -> tuple[Any, StubCompletions]:
    completions = StubCompletions(list(responses))
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def completion(
    model: str = "qwen/qwen3.8-27b",
    text: str = '{"total": 1}',
    finish: str = "stop",
    cost: float | None = 0.0,
) -> Any:
    usage = SimpleNamespace(
        prompt_tokens=120,
        completion_tokens=10,
        prompt_tokens_details=SimpleNamespace(cached_tokens=20),
        cost=cost,
    )
    return SimpleNamespace(
        id="gen-1",
        model=model,
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish)],
        usage=usage,
    )


def api_error(cls: type[openai.APIStatusError], status: int) -> openai.APIStatusError:
    http_request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    return cls("boom", response=httpx.Response(status, request=http_request), body=None)


def test_provider_name_follows_the_host() -> None:
    assert provider_name_for("https://openrouter.ai/api/v1") == "openrouter"
    assert provider_name_for("http://localhost:11434/v1") == "ollama"
    assert provider_name_for("https://api.openai.com/v1") == "openai"


def test_content_conversion() -> None:
    parts = to_openai_content(request().content)
    assert parts[0] == {"type": "text", "text": "Extract."}
    assert parts[1] == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAA="}}


def test_sends_json_schema_response_format_and_maps_usage() -> None:
    client, completions = stub_client(completion(cost=0.00042))
    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "key", client=client)

    response = provider.complete(request())

    call = completions.calls[0]
    assert call["model"] == "qwen/qwen3.8-27b:free"
    assert call["messages"][0] == {"role": "system", "content": "You extract."}
    assert call["messages"][1]["role"] == "user"
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["schema"] == SCHEMA
    assert call["extra_body"] == {"usage": {"include": True}, "reasoning": {"effort": "low"}}
    assert call["temperature"] == 0
    assert response.text == '{"total": 1}'
    assert (response.usage.input_tokens, response.usage.cache_read_tokens) == (100, 20)
    assert response.usage.output_tokens == 10
    assert response.cost_usd == 0.00042
    assert response.served_model == "qwen/qwen3.8-27b"
    assert response.stop_reason == "end_turn"
    assert response.request_id == "gen-1"
    assert response.extra == {"json_mode": "schema"}


def test_falls_back_to_json_object_when_the_schema_format_is_rejected() -> None:
    client, completions = stub_client(
        api_error(openai.BadRequestError, 400),
        completion(model="qwen2.5vl:7b", text='```json\n{"total": 2}\n```'),
    )
    provider = OpenAICompatibleProvider("http://localhost:11434/v1", "ollama", client=client)

    response = provider.complete(request(model="qwen2.5vl:7b"))

    assert [c["response_format"]["type"] for c in completions.calls] == [
        "json_schema",
        "json_object",
    ]
    assert completions.calls[0]["extra_body"] is None
    assert json.loads(response.text) == {"total": 2}
    assert response.extra == {"json_mode": "object"}
    assert response.cost_usd == 0.0  # ollama is free


def test_length_finish_reason_means_truncated() -> None:
    client, _ = stub_client(completion(finish="length"))
    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "key", client=client)
    assert provider.complete(request()).truncated


def test_served_model_mismatch() -> None:
    client, _ = stub_client(completion(model="google/gemma-4-31b-it"))
    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "key", client=client)
    with pytest.raises(LLMError) as info:
        provider.complete(request())
    assert info.value.kind == "served_model"


@pytest.mark.parametrize(
    ("error", "kind", "retryable"),
    [
        (api_error(openai.RateLimitError, 429), "rate_limit", True),
        (api_error(openai.AuthenticationError, 401), "auth", False),
        (api_error(openai.InternalServerError, 502), "server", True),
        (openai.APIConnectionError(request=httpx.Request("POST", "https://x")), "network", True),
    ],
)
def test_errors_are_classified(error: Exception, kind: str, retryable: bool) -> None:
    client, _ = stub_client(error)
    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "key", client=client)
    with pytest.raises(LLMError) as info:
        provider.complete(request())
    assert (info.value.kind, info.value.retryable) == (kind, retryable)


def test_a_second_bad_request_is_reported_not_retried() -> None:
    client, completions = stub_client(
        api_error(openai.BadRequestError, 400), api_error(openai.BadRequestError, 400)
    )
    provider = OpenAICompatibleProvider("https://openrouter.ai/api/v1", "key", client=client)
    with pytest.raises(LLMError) as info:
        provider.complete(request())
    assert info.value.kind == "bad_request"
    assert len(completions.calls) == 2
