import pandas as pd

from world_kpi.scoring import (
    category_scores,
    overall_pressure,
    percentile_rank,
    risk_from_percentile,
    transform_series,
)


def test_percentile_and_direction_are_oriented() -> None:
    history = pd.Series(range(1, 101), index=pd.date_range("2000-01-01", periods=100))
    percentile = percentile_rank(history, 90)
    assert 89 <= percentile <= 90
    assert risk_from_percentile(percentile, "high") > 85
    assert risk_from_percentile(percentile, "low") < 15


def test_two_sided_risk_treats_both_tails_as_adverse() -> None:
    assert risk_from_percentile(2, "two_sided") == 96
    assert risk_from_percentile(98, "two_sided") == 96
    assert risk_from_percentile(50, "two_sided") == 0


def test_yoy_transform_uses_configured_release_frequency() -> None:
    monthly = pd.Series(
        [100 + index for index in range(24)],
        index=pd.date_range("2020-01-01", periods=24, freq="MS"),
    )
    transformed = transform_series(monthly, "yoy_pct", 12).dropna()
    assert round(transformed.iloc[0], 4) == 12.0


def test_overall_pressure_equal_weights_pillars() -> None:
    assert overall_pressure({"Pillar with 30 KPIs": 90, "Pillar with 3 KPIs": 10}) == 50

