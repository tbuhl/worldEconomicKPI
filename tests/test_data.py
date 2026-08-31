import pandas as pd

from world_kpi.data import (
    _annual_duration_series,
    merge_incremental_series,
    summarize_top_tic_holders,
)


def _fact(rows: list[dict]) -> dict:
    return {"units": {"USD": rows}}


def test_sec_concept_transition_prefers_fresh_concept_and_backfills_history() -> None:
    old_rows = [
        {"start": "2020-01-01", "end": "2020-12-31", "filed": "2021-02-01", "form": "10-K", "val": 10},
        {"start": "2021-01-01", "end": "2021-12-31", "filed": "2022-02-01", "form": "10-K", "val": 20},
    ]
    new_rows = [
        {"start": "2021-01-01", "end": "2021-12-31", "filed": "2022-03-01", "form": "10-K", "val": 21},
        {"start": "2022-01-01", "end": "2022-12-31", "filed": "2023-02-01", "form": "10-K", "val": 30},
    ]
    facts = {
        "facts": {
            "us-gaap": {
                "OldConcept": _fact(old_rows),
                "NewConcept": _fact(new_rows),
            }
        }
    }
    series = _annual_duration_series(facts, ("OldConcept", "NewConcept"))
    assert list(series.values) == [10, 21, 30]
    assert series.index[-1] == pd.Timestamp("2022-12-31")


def test_incremental_merge_retains_archive_and_prefers_revisions() -> None:
    cached = pd.Series(
        [10.0, 20.0, 30.0], index=pd.to_datetime(["2000-01-01", "2001-01-01", "2002-01-01"])
    )
    update = pd.Series(
        [31.0, 40.0], index=pd.to_datetime(["2002-01-01", "2003-01-01"])
    )
    merged = merge_incremental_series(cached, update)
    assert merged.index[0] == pd.Timestamp("2000-01-01")
    assert merged.loc["2002-01-01"] == 31.0
    assert merged.loc["2003-01-01"] == 40.0


def test_top_tic_holders_are_dynamic_and_sales_are_ranked_against_own_history() -> None:
    dates = pd.date_range("2024-01-01", periods=13, freq="MS")
    rows = []
    holdings = {
        "Country A": 1_000,
        "Country B": 900,
        "Country C": 800,
        "Country D": 700,
        "Country E": 600,
        "Country F": 100,
    }
    for country, latest_holding in holdings.items():
        for index, date in enumerate(dates):
            latest_flow = -100.0 if country == "Country A" else 10.0
            rows.append(
                {
                    "country": country,
                    "date": date,
                    "for_treas_pos": latest_holding - 12 + index,
                    "for_treas_net": latest_flow if index == 12 else -float(index % 3),
                }
            )

    summary = summarize_top_tic_holders(pd.DataFrame(rows))

    assert summary["Country"].tolist() == [
        "Country A",
        "Country B",
        "Country C",
        "Country D",
        "Country E",
    ]
    assert "Country F" not in summary["Country"].tolist()
    country_a = summary.loc[summary["Country"].eq("Country A")].iloc[0]
    assert country_a["Latest net flow ($bn)"] == -100.0
    assert country_a["Sale percentile"] >= 95
    assert country_a["Assessment"] == "Extreme sale"
