from zipfile import ZipFile, ZipInfo

import pandas as pd

import world_kpi.data as data_module

from world_kpi.data import (
    _annual_duration_series,
    hydrate_seed_cache,
    load_market_metrics,
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


def test_market_loader_survives_when_every_symbol_is_unavailable(monkeypatch) -> None:
    def unavailable(symbol: str) -> pd.Series:
        raise RuntimeError(f"{symbol} unavailable")

    monkeypatch.setattr(data_module, "_yahoo_prices", unavailable)
    metrics, failures = load_market_metrics()

    assert metrics == {}
    assert len(failures) == 11


def test_seed_hydration_only_fills_missing_cache_files(tmp_path) -> None:
    archive = tmp_path / "seed.zip"
    cache = tmp_path / "cache"
    existing = cache / "fred" / "EXISTING.csv"
    existing.parent.mkdir(parents=True)
    existing.write_text("local refresh", encoding="utf-8")
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("fred/EXISTING.csv", "seed value")
        bundle.writestr("fred/MISSING.csv", "seed history")

    extracted = hydrate_seed_cache(archive=archive, cache_dir=cache)

    assert extracted == 1
    assert existing.read_text(encoding="utf-8") == "local refresh"
    assert (cache / "fred" / "MISSING.csv").read_text(encoding="utf-8") == "seed history"


def test_old_seed_does_not_look_like_a_recent_download(tmp_path) -> None:
    archive = tmp_path / "seed.zip"
    cache = tmp_path / "cache"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr(ZipInfo("fred/TEST.csv", (2000, 1, 1, 0, 0, 0)), "date,value\n2000-01-01,1\n")
    hydrate_seed_cache(archive, cache)
    assert not data_module._fresh(cache / "fred" / "TEST.csv", 18)


def test_seed_extends_existing_history_without_replacing_runtime_revisions(tmp_path) -> None:
    archive = tmp_path / "seed.zip"
    cache = tmp_path / "cache"
    target = cache / "fred" / "TEST.csv"
    target.parent.mkdir(parents=True)
    target.write_text("date,value\n2000-01-01,9\n", encoding="utf-8")
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("fred/TEST.csv", "date,value\n2000-01-01,1\n2026-11-01,2\n")
    hydrate_seed_cache(archive, cache)
    result = data_module._read_cached_series(target, "TEST")
    assert result.iloc[0] == 9
    assert result.iloc[-1] == 2


def test_failed_fred_refresh_is_visible_and_preserves_archive(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(data_module, "CACHE_DIR", tmp_path)
    archive = tmp_path / "fred" / "TEST.csv"
    archive.parent.mkdir()
    archive.write_text("date,value\n2000-01-01,1\n", encoding="utf-8")
    monkeypatch.setattr(data_module, "_fresh", lambda *args: False)

    class Offline:
        def get(self, *args, **kwargs):
            raise TimeoutError("offline")

    monkeypatch.setattr(data_module, "_session", Offline)
    data_module.reset_source_health()
    result = data_module.fetch_fred_series("TEST")
    assert result.iloc[-1] == 1
    assert data_module.source_health()[0]["Status"] == "Fallback"
    assert data_module.source_health()[0]["Detail"] == "TimeoutError"
