"""A second provider for any OpenAI-compatible chat-completions endpoint: OpenRouter (free
open-weight vision models), a local Ollama, or OpenAI itself. It exists so the pipeline can be
tried for free and so the results table can put a local model next to Claude.

What does not carry over from the Anthropic provider: prompt caching (server dependent) and the
cost table (OpenRouter reports the cost itself; Ollama is free; anything else is priced as
unknown). The effort setting becomes OpenRouter's `reasoning.effort` and is ignored elsewhere."""

from __future__ import annotations

import json
import time
from typing import Any, cast
from urllib.parse import urlparse

import openai
from openai.types.chat import ChatCompletionMessageParam

from fieldwise.extraction.provider import LLMError, LLMRequest, LLMResponse, LLMUsage

OPENROUTER_HOST = "openrouter.ai"
FINISH_REASONS = {"stop": "end_turn", "length": "max_tokens"}
REASONING_EFFORT = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}


def provider_name_for(base_url: str) -> str:
    host = urlparse(base_url).hostname or ""
    if host.endswith(OPENROUTER_HOST):
        return "openrouter"
    if host in {"localhost", "127.0.0.1"}:
        return "ollama"
    return "openai"


def to_openai_content(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic content blocks → OpenAI content parts."""
    parts: list[dict[str, Any]] = []
    for block in blocks:
        if block["type"] == "text":
            parts.append({"type": "text", "text": block["text"]})
        elif block["type"] == "image":
            source = block["source"]
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{source['media_type']};base64,{source['data']}"},
                }
            )
        else:
            raise ValueError(f"unsupported content block {block['type']!r}")
    return parts


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        *,
        client: Any | None = None,
        max_retries: int = 3,
        timeout: float = 180.0,
        json_mode: str = "schema",
    ) -> None:
        self.base_url = base_url
        self.name = provider_name_for(base_url)
        self.json_mode = json_mode  # schema | object — falls back from schema to object on a 400
        self.client = client or openai.OpenAI(
            base_url=base_url, api_key=api_key or "none", max_retries=max_retries, timeout=timeout
        )

    def _response_format(self, request: LLMRequest, mode: str) -> dict[str, Any]:
        if mode == "schema":
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction",
                    "schema": request.output_schema,
                    "strict": True,
                },
            }
        return {"type": "json_object"}

    def _create(self, request: LLMRequest, mode: str) -> Any:
        messages: list[ChatCompletionMessageParam] = cast(
            list[ChatCompletionMessageParam],
            [
                {"role": "system", "content": request.system},
                {"role": "user", "content": to_openai_content(request.content)},
            ],
        )
        extra_body: dict[str, Any] = {}
        if self.name == "openrouter":
            extra_body["usage"] = {"include": True}
            # Reasoning models spend output tokens on thinking; keep it proportional to effort.
            extra_body["reasoning"] = {"effort": REASONING_EFFORT.get(request.effort, "high")}
        return self.client.chat.completions.create(
            model=request.model,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=0,
            response_format=cast(Any, self._response_format(request, mode)),
            extra_body=extra_body or None,
        )

    def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        mode = self.json_mode
        try:
            try:
                completion = self._create(request, mode)
            except openai.BadRequestError:
                if mode != "schema":
                    raise
                mode = "object"  # the model does not support json_schema; validate ourselves
                completion = self._create(request, mode)
        except openai.RateLimitError as error:
            raise LLMError("rate_limit", str(error), retryable=True) from error
        except openai.AuthenticationError as error:
            raise LLMError("auth", str(error), retryable=False) from error
        except openai.BadRequestError as error:
            raise LLMError("bad_request", str(error), retryable=False) from error
        except openai.APIStatusError as error:
            raise LLMError(
                "server" if error.status_code >= 500 else "bad_request",
                str(error),
                retryable=error.status_code >= 500,
            ) from error
        except openai.APIConnectionError as error:
            raise LLMError("network", str(error), retryable=True) from error
        latency_ms = round((time.perf_counter() - started) * 1000)

        choice = completion.choices[0] if completion.choices else None
        if choice is None:
            raise LLMError("server", "the completion has no choices", retryable=True)
        served = str(completion.model or request.model)
        if _base_model(served) != _base_model(request.model):
            raise LLMError(
                "served_model", f"asked for {request.model}, served by {served}", retryable=False
            )
        text = choice.message.content or ""
        usage = completion.usage
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        cached = _cached_tokens(usage)
        reported_cost = _reported_cost(usage)
        return LLMResponse(
            text=_strip_fences(text),
            usage=LLMUsage(
                input_tokens=max(prompt_tokens - cached, 0),
                cache_read_tokens=cached,
                output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            ),
            served_model=served,
            stop_reason=FINISH_REASONS.get(str(choice.finish_reason), choice.finish_reason),
            latency_ms=latency_ms,
            request_id=getattr(completion, "id", None),
            cost_usd=reported_cost
            if reported_cost is not None
            else (0.0 if self.name == "ollama" else None),
            extra={"json_mode": mode},
        )


def _base_model(model: str) -> str:
    """`qwen/qwen3.8-27b:free` and `qwen/qwen3.8-27b` are the same model."""
    return model.split(":", 1)[0]


def _cached_tokens(usage: Any) -> int:
    details = getattr(usage, "prompt_tokens_details", None)
    return int(getattr(details, "cached_tokens", 0) or 0) if details is not None else 0


def _reported_cost(usage: Any) -> float | None:
    cost = getattr(usage, "cost", None)
    if cost is None and hasattr(usage, "model_extra"):
        cost = (usage.model_extra or {}).get("cost")
    return float(cost) if cost is not None else None


def _strip_fences(text: str) -> str:
    """Some models wrap JSON in ```json fences even in JSON mode."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        return text
    return stripped
