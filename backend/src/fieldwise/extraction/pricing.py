"""List prices (USD per million tokens) of the models the workbench runs, as of 2026-09.
Cost is always derived from the usage block the API returned, never estimated from text."""

from dataclasses import dataclass

from fieldwise.extraction.provider import LLMUsage


@dataclass(frozen=True)
class Price:
    input: float
    output: float

    @property
    def cache_write(self) -> float:
        return self.input * 1.25

    @property
    def cache_read(self) -> float:
        return self.input * 0.10


PRICES: dict[str, Price] = {
    "claude-opus-5": Price(input=5.00, output=25.00),
    "claude-sonnet-5": Price(input=2.00, output=10.00),
    "claude-haiku-4-5": Price(input=1.00, output=5.00),
}


def price_for(model: str) -> Price | None:
    matches = [prefix for prefix in PRICES if model.startswith(prefix)]
    return PRICES[max(matches, key=len)] if matches else None


def cost_usd(model: str, usage: LLMUsage, *, batch: bool = False) -> float | None:
    price = price_for(model)
    if price is None:
        return None
    per_million = (
        usage.input_tokens * price.input
        + usage.cache_write_tokens * price.cache_write
        + usage.cache_read_tokens * price.cache_read
        + usage.output_tokens * price.output
    )
    cost = per_million / 1_000_000
    return round(cost * 0.5 if batch else cost, 6)
