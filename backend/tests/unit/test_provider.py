import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2 as httpx
import pytest

from fieldwise.extraction.provider import (
    AnthropicProvider,
    FakeProvider,
    LLMError,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)

SCHEMA = {"type": "object", "properties": {"total": {"type": "number"}}, "required": ["total"]}


def request(model: str = "claude-sonnet-5") -> LLMRequest:
    return LLMRequest(
        model=model,
        system="You extract.",
        content=[{"type": "text", "text": "Extract."}],
        output_schema=SCHEMA,
        effort="low",
        cache_key={"document": "abc"},
    )


class StubMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def stub_client(messages: StubMessages) -> Any:
    return SimpleNamespace(messages=messages)


def message(model: str = "claude-sonnet-5-20260501", text: str = '{"total": 1}') -> Any:
    return SimpleNamespace(
        model=model,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        usage=SimpleNamespace(
            input_tokens=100,
            cache_creation_input_tokens=50,
            cache_read_input_tokens=25,
            output_tokens=10,
        ),
        stop_reason="end_turn",
        _request_id="req_1",
    )


def api_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    http_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=http_request)
    return cls("boom", response=response, body=None)


def test_anthropic_provider_sends_cached_system_and_structured_output() -> None:
    messages = StubMessages(response=message())
    provider = AnthropicProvider(client=stub_client(messages))

    response = provider.complete(request())

    call = messages.calls[0]
    assert call["model"] == "claude-sonnet-5"
    assert call["max_tokens"] == 4096
    assert call["system"] == [
        {"type": "text", "text": "You extract.", "cache_control": {"type": "ephemeral"}}
    ]
    assert call["messages"] == [{"role": "user", "content": [{"type": "text", "text": "Extract."}]}]
    assert call["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": SCHEMA},
    }
    assert response.text == '{"total": 1}'
    assert response.usage == LLMUsage(100, 50, 25, 10)
    assert response.served_model == "claude-sonnet-5-20260501"
    assert response.request_id == "req_1"
    assert response.stop_reason == "end_turn"
    assert response.latency_ms >= 0
    assert not response.truncated


def test_served_model_mismatch_is_an_error() -> None:
    provider = AnthropicProvider(client=stub_client(StubMessages(response=message(model="other"))))
    with pytest.raises(LLMError) as info:
        provider.complete(request())
    assert info.value.kind == "served_model"
    assert not info.value.retryable


@pytest.mark.parametrize(
    ("error", "kind", "retryable"),
    [
        (api_error(anthropic.RateLimitError, 429), "rate_limit", True),
        (api_error(anthropic.AuthenticationError, 401), "auth", False),
        (api_error(anthropic.BadRequestError, 400), "bad_request", False),
        (api_error(anthropic.InternalServerError, 500), "server", True),
        (anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")), "network", True),
    ],
)
def test_sdk_errors_are_classified(error: Exception, kind: str, retryable: bool) -> None:
    provider = AnthropicProvider(client=stub_client(StubMessages(error=error)))
    with pytest.raises(LLMError) as info:
        provider.complete(request())
    assert info.value.kind == kind
    assert info.value.retryable is retryable
    assert str(info.value).startswith(f"{kind}: ")


def test_fake_provider_serialises_dict_answers_and_records_requests() -> None:
    provider = FakeProvider(lambda req: {"total": 5}, latency_ms=3)
    response = provider.complete(request())
    assert json.loads(response.text) == {"total": 5}
    assert response.served_model == "claude-sonnet-5"
    assert response.latency_ms == 3
    assert provider.requests[0].cache_key == {"document": "abc"}


def test_response_round_trips_through_dict() -> None:
    response = LLMResponse("{}", LLMUsage(1, 2, 3, 4), "m", "max_tokens", 12, "req")
    restored = LLMResponse.from_dict(response.to_dict())
    assert restored == response
    assert restored.truncated
    assert restored.usage.total_input == 6
