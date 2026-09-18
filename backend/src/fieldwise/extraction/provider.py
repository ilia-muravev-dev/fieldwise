"""The one place that talks to the Anthropic SDK, behind a protocol that a fake provider (tests,
the e2e profile) and a recording/replaying cassette provider implement as well."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import anthropic
from anthropic.types import ContentBlockParam, MessageParam, TextBlockParam

ErrorKind = str  # rate_limit | server | network | bad_request | auth | served_model | cassette_miss


class LLMError(Exception):
    def __init__(self, kind: ErrorKind, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable

    def __str__(self) -> str:
        return f"{self.kind}: {super().__str__()}"


@dataclass(frozen=True)
class LLMRequest:
    model: str
    system: str
    content: list[dict[str, Any]]
    output_schema: dict[str, Any]
    effort: str = "low"
    max_tokens: int = 4096
    # Stable identity of the request for the cassette provider: what it was built from, not the
    # bytes it contains (image encoding must not change the key).
    cache_key: dict[str, str] = field(default_factory=dict)

    def messages(self) -> list[MessageParam]:
        return [{"role": "user", "content": cast(list[ContentBlockParam], self.content)}]

    def system_blocks(self) -> list[TextBlockParam]:
        return [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}]


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_input(self) -> int:
        return self.input_tokens + self.cache_write_tokens + self.cache_read_tokens


@dataclass(frozen=True)
class LLMResponse:
    text: str
    usage: LLMUsage
    served_model: str
    stop_reason: str | None
    latency_ms: int
    request_id: str | None = None
    # Cost as reported by the provider (OpenRouter does; Anthropic is priced from the table).
    cost_usd: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def truncated(self) -> bool:
        return self.stop_reason == "max_tokens"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "usage": self.usage.__dict__,
            "served_model": self.served_model,
            "stop_reason": self.stop_reason,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
            "cost_usd": self.cost_usd,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLMResponse:
        return cls(
            text=str(data["text"]),
            usage=LLMUsage(**data["usage"]),
            served_model=str(data["served_model"]),
            stop_reason=data.get("stop_reason"),
            latency_ms=int(data.get("latency_ms", 0)),
            request_id=data.get("request_id"),
            cost_usd=data.get("cost_usd"),
            extra=dict(data.get("extra") or {}),
        )


class LLMProvider(Protocol):
    name: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        *,
        max_retries: int = 3,
        timeout: float = 180.0,
    ) -> None:
        self.client = client or anthropic.Anthropic(max_retries=max_retries, timeout=timeout)

    def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        try:
            message = self.client.messages.create(
                model=request.model,
                max_tokens=request.max_tokens,
                system=request.system_blocks(),
                messages=request.messages(),
                output_config={
                    "effort": cast(Any, request.effort),
                    "format": {"type": "json_schema", "schema": request.output_schema},
                },
            )
        except anthropic.RateLimitError as error:
            raise LLMError("rate_limit", str(error), retryable=True) from error
        except anthropic.AuthenticationError as error:
            raise LLMError("auth", str(error), retryable=False) from error
        except anthropic.BadRequestError as error:
            raise LLMError("bad_request", str(error), retryable=False) from error
        except anthropic.APIStatusError as error:
            raise LLMError(
                "server" if error.status_code >= 500 else "bad_request",
                str(error),
                retryable=error.status_code >= 500,
            ) from error
        except anthropic.APIConnectionError as error:
            raise LLMError("network", str(error), retryable=True) from error
        latency_ms = round((time.perf_counter() - started) * 1000)

        if not message.model.startswith(request.model):
            raise LLMError(
                "served_model",
                f"asked for {request.model}, served by {message.model}",
                retryable=False,
            )
        text = "".join(block.text for block in message.content if block.type == "text")
        usage = LLMUsage(
            input_tokens=message.usage.input_tokens,
            cache_write_tokens=message.usage.cache_creation_input_tokens or 0,
            cache_read_tokens=message.usage.cache_read_input_tokens or 0,
            output_tokens=message.usage.output_tokens,
        )
        return LLMResponse(
            text=text,
            usage=usage,
            served_model=message.model,
            stop_reason=message.stop_reason,
            latency_ms=latency_ms,
            request_id=message._request_id,
        )


Responder = Callable[[LLMRequest], dict[str, Any] | str]


class FakeProvider:
    """Answers from a callable. Used by tests and by the `LLM_PROVIDER=fake` profile."""

    name = "fake"

    def __init__(
        self,
        responder: Responder,
        *,
        served_model: str | None = None,
        stop_reason: str | None = "end_turn",
        latency_ms: int = 1,
    ) -> None:
        self.responder = responder
        self.served_model = served_model
        self.stop_reason = stop_reason
        self.latency_ms = latency_ms
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        answer = self.responder(request)
        text = answer if isinstance(answer, str) else json.dumps(answer)
        prompt_chars = len(request.system) + sum(
            len(str(block.get("text", ""))) for block in request.content
        )
        return LLMResponse(
            text=text,
            usage=LLMUsage(input_tokens=prompt_chars // 4, output_tokens=len(text) // 4),
            served_model=self.served_model or request.model,
            stop_reason=self.stop_reason,
            latency_ms=self.latency_ms,
        )
