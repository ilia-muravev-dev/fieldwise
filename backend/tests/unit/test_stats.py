from fieldwise.evals.stats import Proportion, fmt_pct, percentile


def test_wilson_interval_brackets_the_point_estimate() -> None:
    low, high = Proportion(93, 100).wilson()  # type: ignore[misc]
    assert 0.86 < low < 0.93 < high < 0.97
    assert Proportion(0, 0).wilson() is None
    assert Proportion(0, 0).value is None
    assert Proportion(10, 10).wilson() == (Proportion(10, 10).wilson() or (0, 0))


def test_percentile_and_formatting() -> None:
    values = [float(v) for v in range(1, 101)]
    assert percentile(values, 50) == 50.0
    assert percentile(values, 95) == 95.0
    assert percentile([], 50) is None
    assert fmt_pct(0.934) == "93.4%"
    assert fmt_pct(None) == "—"
