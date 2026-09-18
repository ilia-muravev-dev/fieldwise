"""Builds the configured provider: the real one, the fake, optionally wrapped in a cassette."""

from pathlib import Path
from typing import Any, cast

from fieldwise.config import Settings
from fieldwise.extraction.cassette import CassetteMode, CassetteProvider
from fieldwise.extraction.openai_compat import OpenAICompatibleProvider
from fieldwise.extraction.provider import AnthropicProvider, FakeProvider, LLMProvider, LLMRequest


def empty_answer(request: LLMRequest) -> dict[str, Any]:
    """The fake provider's default: a schema-valid object with every leaf null and lists empty."""
    return cast(dict[str, Any], _empty_for(request.output_schema))


def _empty_for(schema: dict[str, Any]) -> Any:
    if schema.get("type") == "object":
        return {key: _empty_for(child) for key, child in schema.get("properties", {}).items()}
    if schema.get("type") == "array":
        return []
    return None


def build_provider(
    settings: Settings,
    *,
    provider_name: str | None = None,
    cassette_mode: CassetteMode | None = None,
    cassette_dir: Path | None = None,
) -> LLMProvider:
    name = provider_name or settings.llm_provider
    inner: LLMProvider
    if name == "fake":
        inner = FakeProvider(empty_answer)
    elif name == "anthropic":
        inner = AnthropicProvider()
    elif name == "openai":
        inner = OpenAICompatibleProvider(settings.openai_base_url, settings.openai_api_key)
    else:
        raise ValueError(f"unknown provider {name!r}")
    mode = cassette_mode or settings.llm_cassette_mode
    if mode == "off":
        return inner
    return CassetteProvider(inner, cassette_dir or Path(settings.llm_cassette_dir), mode)


def describe(provider: LLMProvider) -> str:
    if isinstance(provider, CassetteProvider):
        return f"{provider.inner.name} (cassette: {provider.mode})"
    return provider.name
