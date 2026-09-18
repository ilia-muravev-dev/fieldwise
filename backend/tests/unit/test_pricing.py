from fieldwise.extraction.pricing import cost_usd, price_for
from fieldwise.extraction.provider import LLMUsage


def test_price_lookup_uses_the_longest_matching_prefix() -> None:
    assert price_for("claude-sonnet-5").input == 2.0
    assert price_for("claude-sonnet-5-20260501").output == 10.0
    assert price_for("claude-haiku-4-5").input == 1.0
    assert price_for("gpt-x") is None


def test_cost_from_usage_including_cache_rates() -> None:
    usage = LLMUsage(
        input_tokens=1_000_000, cache_write_tokens=0, cache_read_tokens=0, output_tokens=0
    )
    assert cost_usd("claude-sonnet-5", usage) == 2.0
    cached = LLMUsage(
        input_tokens=0,
        cache_write_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        output_tokens=100_000,
    )
    assert cost_usd("claude-sonnet-5", cached) == round(2.5 + 0.2 + 1.0, 6)
    assert cost_usd("claude-sonnet-5", cached, batch=True) == round((2.5 + 0.2 + 1.0) / 2, 6)
    assert cost_usd("unknown-model", usage) is None
