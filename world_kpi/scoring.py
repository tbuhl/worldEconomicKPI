from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass
class MetricSnapshot:
    key: str
    name: str
    category: str
    value: float
    unit: str
    as_of: pd.Timestamp
    risk_score: float
    percentile: float
    direction: str
    weight: float
    change: float | None
    history: pd.Series
    why: str = ""
    watch: str = ""
    source_name: str = ""
    source_url: str = ""
    frequency: str = ""

    @property
    def state(self) -> str:
        return risk_label(self.risk_score)


def clean_series(series: pd.Series) -> pd.Series:
    result = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    result.index = pd.to_datetime(result.index, errors="coerce")
    result = result[~result.index.isna()].sort_index()
    return result[~result.index.duplicated(keep="last")]


def transform_series(series: pd.Series, transform: str, periods_per_year: int) -> pd.Series:
    series = clean_series(series)
    if transform == "level":
        return series
    if transform == "yoy_pct":
        return series.pct_change(periods_per_year, fill_method=None) * 100
    if transform == "yoy_change":
        return series.diff(periods_per_year)
    raise ValueError(f"Unknown transform: {transform}")


def percentile_rank(history: pd.Series, value: float) -> float:
    history = clean_series(history)
    if history.empty or pd.isna(value):
        return float("nan")
    # Mid-rank makes tied, slow-moving policy series less jumpy.
    less = float((history < value).sum())
    equal = float((history == value).sum())
    return 100.0 * (less + 0.5 * equal) / len(history)


def risk_from_percentile(percentile: float, direction: str) -> float:
    if pd.isna(percentile):
        return float("nan")
    if direction == "high":
        return float(percentile)
    if direction == "low":
        return float(100 - percentile)
    if direction == "two_sided":
        return float(abs(percentile - 50) * 2)
    raise ValueError(f"Unknown risk direction: {direction}")


def risk_label(score: float) -> str:
    if pd.isna(score):
        return "Unavailable"
    if score >= 85:
        return "Severe"
    if score >= 70:
        return "Elevated"
    if score >= 50:
        return "Watch"
    return "Calm"


def score_at_date(
    series: pd.Series,
    when: str | pd.Timestamp,
    direction: str,
    reference: pd.Series | None = None,
) -> tuple[float, float, pd.Timestamp | None]:
    series = clean_series(series)
    if series.empty:
        return float("nan"), float("nan"), None
    when = pd.Timestamp(when)
    available = series.loc[:when]
    if available.empty:
        return float("nan"), float("nan"), None
    value = float(available.iloc[-1])
    reference = clean_series(reference if reference is not None else series)
    # Avoid comparing a 2000 observation with data that did not exist until much later.
    reference = reference.loc[: max(when, reference.index.min())] if when < series.index.max() else reference
    if len(reference) < 12:
        reference = series
    pct = percentile_rank(reference, value)
    return risk_from_percentile(pct, direction), value, available.index[-1]


def category_scores(metrics: Iterable[MetricSnapshot]) -> dict[str, float]:
    frame = pd.DataFrame(
        [
            {"category": metric.category, "score": metric.risk_score, "weight": metric.weight}
            for metric in metrics
            if not pd.isna(metric.risk_score)
        ]
    )
    if frame.empty:
        return {}
    scores: dict[str, float] = {}
    for category, group in frame.groupby("category", sort=False):
        scores[str(category)] = float(np.average(group["score"], weights=group["weight"]))
    return scores


def overall_pressure(category_values: dict[str, float]) -> float:
    if not category_values:
        return float("nan")
    # Pillars are equal-weighted. This is a breadth gauge, not a probability of collapse.
    return float(np.mean(list(category_values.values())))


def historical_category_scores(
    metrics: Iterable[MetricSnapshot], dates: dict[str, str]
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    metrics = list(metrics)
    for label, date in dates.items():
        category_rows: list[dict[str, object]] = []
        for metric in metrics:
            score, _, _ = score_at_date(metric.history, date, metric.direction, metric.history)
            if not pd.isna(score):
                category_rows.append(
                    {"category": metric.category, "score": score, "weight": metric.weight}
                )
        if not category_rows:
            continue
        frame = pd.DataFrame(category_rows)
        for category, group in frame.groupby("category", sort=False):
            rows.append(
                {
                    "period": label,
                    "category": category,
                    "score": float(np.average(group["score"], weights=group["weight"])),
                    "coverage": int(len(group)),
                }
            )
    return pd.DataFrame(rows)


def describe_metric(metric: MetricSnapshot) -> str:
    trend = "little changed"
    if metric.change is not None and not pd.isna(metric.change):
        if metric.change > 0:
            trend = "up from the prior reading"
        elif metric.change < 0:
            trend = "down from the prior reading"
    tail = (
        f"It sits at the {metric.percentile:.0f}th percentile of its available history and is "
        f"{trend}."
    )
    if metric.direction == "low":
        tail = (
            f"It sits at the {metric.percentile:.0f}th percentile of its available history; lower "
            f"readings are treated as riskier. It is {trend}."
        )
    elif metric.direction == "two_sided":
        tail = (
            f"It sits at the {metric.percentile:.0f}th percentile; distance from normal in either "
            f"direction is treated as risk. It is {trend}."
        )
    return f"{metric.why} {tail}"

