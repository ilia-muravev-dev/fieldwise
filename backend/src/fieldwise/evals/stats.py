"""Small statistics helpers: Wilson intervals for accuracies, percentiles for latencies."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Proportion:
    correct: int
    total: int

    @property
    def value(self) -> float | None:
        return self.correct / self.total if self.total else None

    def wilson(self, z: float = 1.96) -> tuple[float, float] | None:
        if self.total == 0:
            return None
        n, p = self.total, self.correct / self.total
        denominator = 1 + z * z / n
        centre = (p + z * z / (2 * n)) / denominator
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
        return (max(0.0, centre - half), min(1.0, centre + half))


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile; p in [0, 100]."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"
