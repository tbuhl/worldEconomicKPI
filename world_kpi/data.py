from __future__ import annotations

import io
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

from world_kpi.catalog import FRED_INDICATORS, MARKET_METRIC_META, Indicator
from world_kpi.scoring import MetricSnapshot, clean_series, percentile_rank, risk_from_percentile, transform_series


FRED_GRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FISCAL_DATA = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
TIC_TABLE3 = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table3.txt"
SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
USER_AGENT = os.getenv(
    "WORLD_KPI_USER_AGENT", "WorldKPI-Radar/0.1 research dashboard contact: local-user"
)
CACHE_DIR = Path(os.getenv("WORLD_KPI_CACHE", ".world_kpi_cache"))


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    return session


def _cache_path(namespace: str, key: str, suffix: str) -> Path:
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in key)
    path = CACHE_DIR / namespace / f"{safe}.{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _fresh(path: Path, max_age_hours: float) -> bool:
    return path.exists() and time.time() - path.stat().st_mtime < max_age_hours * 3600


def _get_bytes(url: str, *, cache: Path, max_age_hours: float, timeout: int = 20) -> bytes:
    if _fresh(cache, max_age_hours):
        return cache.read_bytes()
    try:
        response = _session().get(url, timeout=timeout)
        response.raise_for_status()
        content = response.content
        if len(content) < 10:
            raise ValueError(f"Empty response from {url}")
        cache.write_bytes(content)
        return content
    except Exception:
        if cache.exists():
            return cache.read_bytes()
        raise


def _read_cached_series(path: Path, name: str) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float, name=name)
    try:
        frame = pd.read_csv(path)
        if frame.shape[1] < 2:
            return pd.Series(dtype=float, name=name)
        return clean_series(
            pd.Series(
                pd.to_numeric(frame.iloc[:, 1], errors="coerce").to_numpy(),
                index=pd.to_datetime(frame.iloc[:, 0], errors="coerce"),
                name=name,
            )
        )
    except Exception:
        return pd.Series(dtype=float, name=name)


def _store_series(series: pd.Series, path: Path) -> None:
    series = clean_series(series)
    series.rename("value").to_csv(path, index_label="date")


def merge_incremental_series(cached: pd.Series, update: pd.Series) -> pd.Series:
    """Merge a recent refresh into a persistent archive, preferring revised observations."""
    cached = clean_series(cached)
    update = clean_series(update)
    if cached.empty:
        return update
    if update.empty:
        return cached
    return clean_series(pd.concat([cached, update]).loc[lambda values: ~values.index.duplicated(keep="last")])


def fetch_fred_series(series_id: str, start: str = "1990-01-01") -> pd.Series:
    archive = _cache_path("fred", series_id, "csv")
    cached = _read_cached_series(archive, series_id)
    if not cached.empty and _fresh(archive, 18):
        return cached

    requested_start = pd.Timestamp(start)
    if not cached.empty:
        # A two-year overlap captures most routine revisions while retaining the older archive.
        requested_start = max(requested_start, cached.index[-1] - pd.DateOffset(years=2))
    url = f"{FRED_GRAPH}?id={quote(series_id)}&cosd={requested_start:%Y-%m-%d}"
    try:
        response = _session().get(url, timeout=20)
        response.raise_for_status()
        frame = pd.read_csv(io.BytesIO(response.content))
        if frame.shape[1] < 2:
            raise ValueError(f"Unexpected FRED response for {series_id}")
        update = clean_series(
            pd.Series(
                pd.to_numeric(frame.iloc[:, 1], errors="coerce").to_numpy(),
                index=pd.to_datetime(frame.iloc[:, 0], errors="coerce"),
                name=series_id,
            )
        )
        combined = merge_incremental_series(cached, update)
        _store_series(combined, archive)
        return combined
    except Exception:
        if not cached.empty:
            return cached
        raise


def load_fred_bundle(
    indicators: Iterable[Indicator] = FRED_INDICATORS,
) -> tuple[dict[str, pd.Series], dict[str, str]]:
    indicators = list(indicators)
    results: dict[str, pd.Series] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        jobs = {
            executor.submit(fetch_fred_series, indicator.series_id): indicator
            for indicator in indicators
        }
        for future in as_completed(jobs):
            indicator = jobs[future]
            try:
                results[indicator.key] = transform_series(
                    future.result(), indicator.transform, indicator.periods_per_year
                )
            except Exception as exc:  # keep the dashboard useful during partial outages
                failures[indicator.key] = str(exc)
    return results, failures


def build_fred_snapshots(series_by_key: dict[str, pd.Series]) -> list[MetricSnapshot]:
    metrics: list[MetricSnapshot] = []
    for indicator in FRED_INDICATORS:
        history = clean_series(series_by_key.get(indicator.key, pd.Series(dtype=float)))
        if history.empty:
            continue
        current = float(history.iloc[-1])
        reference = history.loc[history.index >= pd.Timestamp("1990-01-01")]
        if len(reference) < 24:
            reference = history
        percentile = percentile_rank(reference, current)
        change = float(history.iloc[-1] - history.iloc[-2]) if len(history) > 1 else None
        metrics.append(
            MetricSnapshot(
                key=indicator.key,
                name=indicator.name,
                category=indicator.category,
                value=current,
                unit=indicator.unit,
                as_of=history.index[-1],
                risk_score=risk_from_percentile(percentile, indicator.risk_direction),
                percentile=percentile,
                direction=indicator.risk_direction,
                weight=indicator.weight,
                change=change,
                history=history,
                why=indicator.why,
                watch=indicator.watch,
                source_name=indicator.source_name,
                source_url=indicator.source_url,
                frequency=indicator.frequency,
            )
        )
    return metrics


def load_daily_debt() -> pd.Series:
    query = "?sort=record_date&page%5Bsize%5D=10000&fields=record_date,tot_pub_debt_out_amt"
    payload = _get_bytes(
        FISCAL_DATA + query,
        cache=_cache_path("treasury", "debt_to_penny", "json"),
        max_age_hours=18,
    )
    data = json.loads(payload)["data"]
    frame = pd.DataFrame(data)
    return clean_series(
        pd.Series(
            pd.to_numeric(frame["tot_pub_debt_out_amt"], errors="coerce").to_numpy() / 1e12,
            index=pd.to_datetime(frame["record_date"]),
            name="total_public_debt",
        )
    )


TIC_NUMERIC_COLUMNS = (
    "for_treas_pos",
    "for_treas_net",
    "for_lt_treas_pos",
    "for_lt_treas_net",
    "for_lt_treas_valchg",
    "for_st_treas_pos",
    "for_st_treas_net",
)
TIC_NON_COUNTRY_ROWS = {
    "All Countries",
    "Grand Total",
    "International",
    "Total IROs",
    "Total Regional Orgs.",
}


def load_tic_holdings() -> pd.DataFrame:
    """Load country-level Treasury holdings and net flows in USD billions."""
    payload = _get_bytes(
        TIC_TABLE3,
        cache=_cache_path("treasury", "tic_table3", "txt"),
        max_age_hours=36 * 24,
    )
    text = payload.decode("utf-8", errors="replace")
    # Treasury includes a title block and two header rows; the second header is machine-readable.
    frame = pd.read_csv(io.StringIO(text), sep="\t", skiprows=8, dtype=str)
    frame.columns = [column.strip() for column in frame.columns]
    frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m", errors="coerce")
    frame = frame[
        ~frame["country"].isin(TIC_NON_COUNTRY_ROWS)
        & ~frame["country"].str.startswith(("Total ", "Memo:", "Of Which:"), na=False)
    ].copy()
    for column in TIC_NUMERIC_COLUMNS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce") / 1000  # $bn
    return frame.dropna(subset=["date", "country"]).sort_values(["date", "country"])


def summarize_top_tic_holders(tic: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """Summarize the latest largest holders and contextualize reported net selling.

    TIC's ``for_treas_net`` is net U.S. sales to foreign residents: positive values
    indicate net foreign purchases and negative values indicate net foreign sales.
    The sale percentile ranks ``max(-net_flow, 0)`` against the country's available
    monthly history, so a large current sale receives a high percentile.
    """
    columns = [
        "Country",
        "Holdings ($bn)",
        "Holdings change ($bn)",
        "Latest net flow ($bn)",
        "3m net flow ($bn)",
        "12m holdings change (%)",
        "Sale percentile",
        "Assessment",
        "As of",
    ]
    required = {"country", "date", "for_treas_pos", "for_treas_net"}
    if tic.empty or not required.issubset(tic.columns):
        return pd.DataFrame(columns=columns)

    frame = tic.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date", "country", "for_treas_pos"])
    if frame.empty:
        return pd.DataFrame(columns=columns)

    latest_date = frame["date"].max()
    leaders = (
        frame.loc[frame["date"].eq(latest_date)]
        .nlargest(top_n, "for_treas_pos")["country"]
        .tolist()
    )
    rows: list[dict[str, Any]] = []
    for country in leaders:
        history = frame.loc[frame["country"].eq(country)].sort_values("date")
        latest = history.iloc[-1]
        holdings = pd.to_numeric(history["for_treas_pos"], errors="coerce")
        flows = pd.to_numeric(history["for_treas_net"], errors="coerce")
        latest_flow = float(flows.iloc[-1]) if pd.notna(flows.iloc[-1]) else np.nan
        sales = (-flows).clip(lower=0).dropna()
        if sales.empty or pd.isna(latest_flow):
            sale_percentile = np.nan
        elif latest_flow >= 0:
            sale_percentile = 0.0
        else:
            latest_sale = max(-latest_flow, 0.0)
            sale_percentile = 100 * (
                float((sales < latest_sale).sum()) + 0.5 * float((sales == latest_sale).sum())
            ) / len(sales)

        if pd.isna(latest_flow):
            assessment = "Unavailable"
        elif latest_flow >= 0:
            assessment = "Net buyer"
        elif sale_percentile >= 95:
            assessment = "Extreme sale"
        elif sale_percentile >= 80:
            assessment = "Unusual sale"
        elif sale_percentile >= 65:
            assessment = "Elevated sale"
        else:
            assessment = "Typical sale"

        rows.append(
            {
                "Country": country,
                "Holdings ($bn)": float(holdings.iloc[-1]),
                "Holdings change ($bn)": (
                    float(holdings.iloc[-1] - holdings.iloc[-2]) if len(holdings) > 1 else np.nan
                ),
                "Latest net flow ($bn)": latest_flow,
                "3m net flow ($bn)": float(flows.tail(3).sum(min_count=1)),
                "12m holdings change (%)": (
                    float((holdings.iloc[-1] / holdings.iloc[-13] - 1) * 100)
                    if len(holdings) >= 13 and holdings.iloc[-13]
                    else np.nan
                ),
                "Sale percentile": sale_percentile,
                "Assessment": assessment,
                "As of": pd.Timestamp(latest["date"]),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _fetch_yahoo_chart(symbol: str, start: pd.Timestamp) -> tuple[pd.Series, bool]:
    period1 = int(pd.Timestamp(start, tz="UTC").timestamp())
    period2 = int((pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=2)).timestamp())
    url = (
        YAHOO_CHART.format(symbol=quote(symbol, safe=""))
        + f"?period1={period1}&period2={period2}&interval=1d&events=history"
    )
    response = _session().get(url, timeout=20)
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    timestamps = pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_localize(None)
    quote_data = result["indicators"]["quote"][0]
    prices = quote_data.get("close", [])
    split_occurred = bool(result.get("events", {}).get("splits"))
    return clean_series(pd.Series(prices, index=timestamps, name=symbol)), split_occurred


def _yahoo_prices(symbol: str, start: str = "1990-01-01") -> pd.Series:
    archive = _cache_path("markets", symbol, "csv")
    cached = _read_cached_series(archive, symbol)
    if not cached.empty and _fresh(archive, 8):
        return cached

    full_start = pd.Timestamp(start)
    update_start = full_start if cached.empty else max(full_start, cached.index[-1] - pd.Timedelta(days=45))
    try:
        update, split_occurred = _fetch_yahoo_chart(symbol, update_start)
        # A split changes the scale of old closing prices, so rebuild that rare archive once.
        if split_occurred and not cached.empty:
            update, _ = _fetch_yahoo_chart(symbol, full_start)
            cached = pd.Series(dtype=float, name=symbol)
        combined = merge_incremental_series(cached, update)
        _store_series(combined, archive)
        return combined
    except Exception:
        if not cached.empty:
            return cached
        raise


def load_market_metrics() -> tuple[dict[str, pd.Series], dict[str, str]]:
    symbols = ("SPY", "QQQ", "RSP", "SOXX", "NVDA", "MSFT", "GOOGL", "AMZN", "META", "ORCL", "PLTR")
    prices: dict[str, pd.Series] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        jobs = {executor.submit(_yahoo_prices, symbol): symbol for symbol in symbols}
        for future in as_completed(jobs):
            symbol = jobs[future]
            try:
                prices[symbol] = future.result()
            except Exception as exc:
                failures[symbol] = str(exc)

    metrics: dict[str, pd.Series] = {}
    if "SPY" in prices:
        spy = prices["SPY"]
        metrics["spy_drawdown"] = (spy / spy.cummax() - 1) * 100
        metrics["spy_volatility"] = spy.pct_change(fill_method=None).rolling(30).std() * math.sqrt(252) * 100
    if "QQQ" in prices and "SPY" in prices:
        aligned = pd.concat([prices["QQQ"], prices["SPY"]], axis=1).dropna()
        metrics["qqq_spy"] = (aligned.iloc[:, 0] / aligned.iloc[:, 1]).pct_change(252, fill_method=None) * 100
    if "RSP" in prices and "SPY" in prices:
        aligned = pd.concat([prices["RSP"], prices["SPY"]], axis=1).dropna()
        metrics["breadth"] = (aligned.iloc[:, 0] / aligned.iloc[:, 1]).pct_change(252, fill_method=None) * 100
    if "SOXX" in prices:
        semis = prices["SOXX"]
        metrics["semis_return"] = semis.pct_change(252, fill_method=None) * 100
        metrics["semis_drawdown"] = (semis / semis.cummax() - 1) * 100

    ai_returns = pd.concat(
        [series.pct_change(fill_method=None).rename(symbol) for symbol, series in prices.items() if symbol in {"NVDA", "MSFT", "GOOGL", "AMZN", "META", "ORCL", "PLTR"}],
        axis=1,
    )
    if not ai_returns.empty:
        # Require at least four live constituents to avoid a single-stock history masquerading as a basket.
        basket_returns = ai_returns.mean(axis=1, skipna=True).where(ai_returns.count(axis=1) >= 4)
        basket_index = (1 + basket_returns.fillna(0)).cumprod()
        metrics["ai_basket_return"] = basket_index.pct_change(252, fill_method=None) * 100
        metrics["ai_basket_vol"] = basket_returns.rolling(30).std() * math.sqrt(252) * 100
    return {key: clean_series(value) for key, value in metrics.items()}, failures


def build_market_snapshots(series_by_key: dict[str, pd.Series]) -> list[MetricSnapshot]:
    metrics: list[MetricSnapshot] = []
    for key, meta in MARKET_METRIC_META.items():
        history = clean_series(series_by_key.get(key, pd.Series(dtype=float)))
        if history.empty:
            continue
        current = float(history.iloc[-1])
        reference = history.loc[history.index >= pd.Timestamp("2000-01-01")]
        if len(reference) < 60:
            reference = history
        percentile = percentile_rank(reference, current)
        direction = str(meta["direction"])
        metrics.append(
            MetricSnapshot(
                key=key,
                name=str(meta["name"]),
                category=str(meta["category"]),
                value=current,
                unit=str(meta["unit"]),
                as_of=history.index[-1],
                risk_score=risk_from_percentile(percentile, direction),
                percentile=percentile,
                direction=direction,
                weight=float(meta["weight"]),
                change=float(history.iloc[-1] - history.iloc[-2]) if len(history) > 1 else None,
                history=history,
                why=str(meta["why"]),
                watch="Price signals can reverse quickly and are not a substitute for cash-flow valuation.",
                source_name="Yahoo Finance market data",
                source_url="https://finance.yahoo.com/markets/",
                frequency="Daily",
            )
        )
    return metrics


SEC_COMPANIES = {
    "Microsoft": "0000789019",
    "Alphabet": "0001652044",
    "Meta": "0001326801",
    "Amazon": "0001018724",
    "Oracle": "0001341439",
    "NVIDIA": "0001045810",
}
CAPEX_CONCEPTS = (
    "PaymentsToAcquireProductiveAssets",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForAdditionsToPropertyPlantAndEquipment",
    "PropertyPlantAndEquipmentAdditions",
)
OCF_CONCEPTS = ("NetCashProvidedByUsedInOperatingActivities",)
REVENUE_CONCEPTS = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet")


def _load_company_facts(cik: str) -> dict[str, Any]:
    payload = _get_bytes(
        SEC_FACTS.format(cik=cik),
        cache=_cache_path("sec", cik, "json"),
        max_age_hours=24,
        timeout=30,
    )
    return json.loads(payload)


def _find_concept(facts: dict[str, Any], concepts: Iterable[str]) -> dict[str, Any] | None:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for concept in concepts:
        if concept in us_gaap:
            return us_gaap[concept]
    return None


def _annual_duration_series(facts: dict[str, Any], concepts: Iterable[str]) -> pd.Series:
    candidates: list[pd.Series] = []
    for concept_name in concepts:
        concept = _find_concept(facts, (concept_name,))
        if not concept:
            continue
        rows = concept.get("units", {}).get("USD", [])
        frame = pd.DataFrame(rows)
        if frame.empty or "start" not in frame or "end" not in frame:
            continue
        frame = frame[frame["form"].isin(["10-K", "20-F"])].copy()
        frame["start"] = pd.to_datetime(frame["start"], errors="coerce")
        frame["end"] = pd.to_datetime(frame["end"], errors="coerce")
        frame["filed"] = pd.to_datetime(frame["filed"], errors="coerce")
        frame["duration"] = (frame["end"] - frame["start"]).dt.days
        frame = frame[frame["duration"].between(300, 430)]
        frame = frame.sort_values("filed").drop_duplicates("end", keep="last")
        series = clean_series(
            pd.Series(pd.to_numeric(frame["val"], errors="coerce").to_numpy(), index=frame["end"])
        )
        if not series.empty:
            candidates.append(series)
    if not candidates:
        return pd.Series(dtype=float)
    # Filers sometimes retire one US-GAAP concept and adopt another. Prefer the concept with
    # the freshest observation, then backfill non-overlapping years from older concepts.
    candidates.sort(key=lambda series: (series.index[-1], len(series)), reverse=True)
    result = candidates[0]
    for candidate in candidates[1:]:
        result = result.combine_first(candidate)
    return clean_series(result)


def _annual_instant_series(facts: dict[str, Any], concepts: Iterable[str]) -> pd.Series:
    concept = _find_concept(facts, concepts)
    if not concept:
        return pd.Series(dtype=float)
    rows = concept.get("units", {}).get("USD", [])
    frame = pd.DataFrame(rows)
    if frame.empty or "end" not in frame:
        return pd.Series(dtype=float)
    frame = frame[frame["form"].isin(["10-K", "20-F"])].copy()
    frame["end"] = pd.to_datetime(frame["end"], errors="coerce")
    frame["filed"] = pd.to_datetime(frame["filed"], errors="coerce")
    if "fp" in frame:
        frame = frame[frame["fp"].eq("FY")]
    frame = frame.sort_values("filed").drop_duplicates("end", keep="last")
    return clean_series(pd.Series(pd.to_numeric(frame["val"], errors="coerce").to_numpy(), index=frame["end"]))


def load_sec_ai_metrics() -> tuple[dict[str, pd.Series], pd.DataFrame, dict[str, str]]:
    facts_by_company: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = {executor.submit(_load_company_facts, cik): company for company, cik in SEC_COMPANIES.items()}
        for future in as_completed(jobs):
            company = jobs[future]
            try:
                facts_by_company[company] = future.result()
            except Exception as exc:
                failures[company] = str(exc)

    histories: dict[str, dict[str, pd.Series]] = {}
    company_rows: list[dict[str, Any]] = []
    for company, facts in facts_by_company.items():
        capex = _annual_duration_series(facts, CAPEX_CONCEPTS).abs()
        ocf = _annual_duration_series(facts, OCF_CONCEPTS)
        revenue = _annual_duration_series(facts, REVENUE_CONCEPTS)
        histories[company] = {"capex": capex, "ocf": ocf, "revenue": revenue}
        company_rows.append(
            {
                "Company": company,
                "Capex · latest FY ($bn)": capex.iloc[-1] / 1e9 if not capex.empty else np.nan,
                "Capex growth": capex.pct_change(fill_method=None).iloc[-1] * 100 if len(capex) > 1 else np.nan,
                "Capex / operating cash flow": capex.iloc[-1] / ocf.iloc[-1] * 100 if not capex.empty and not ocf.empty and ocf.iloc[-1] else np.nan,
                "Filed through": max([series.index[-1] for series in (capex, ocf, revenue) if not series.empty], default=pd.NaT),
            }
        )

    aggregate_rows: list[dict[str, float]] = []
    for year in range(2010, pd.Timestamp.now().year + 1):
        capex_values: list[float] = []
        ocf_values: list[float] = []
        revenue_values: list[float] = []
        for company in ("Microsoft", "Alphabet", "Meta", "Amazon", "Oracle"):
            company_history = histories.get(company, {})
            for collection, values in ((capex_values, company_history.get("capex")), (ocf_values, company_history.get("ocf")), (revenue_values, company_history.get("revenue"))):
                if values is not None and not values.empty:
                    match = values[values.index.year == year]
                    if not match.empty:
                        collection.append(float(match.iloc[-1]))
        if len(capex_values) >= 3:
            aggregate_rows.append(
                {
                    "date": pd.Timestamp(f"{year}-12-31"),
                    "capex": sum(capex_values) / 1e9,
                    "ocf": sum(ocf_values) / 1e9 if len(ocf_values) >= 3 else np.nan,
                    "revenue": sum(revenue_values) / 1e9 if len(revenue_values) >= 3 else np.nan,
                }
            )
    aggregate = pd.DataFrame(aggregate_rows).set_index("date") if aggregate_rows else pd.DataFrame()
    metrics: dict[str, pd.Series] = {}
    if not aggregate.empty:
        metrics["hyperscaler_capex"] = aggregate["capex"]
        metrics["capex_growth"] = aggregate["capex"].pct_change(fill_method=None) * 100
        metrics["capex_to_ocf"] = aggregate["capex"] / aggregate["ocf"] * 100
        metrics["capex_to_revenue"] = aggregate["capex"] / aggregate["revenue"] * 100

    nvda = facts_by_company.get("NVIDIA", {})
    inventory = _annual_instant_series(nvda, ("InventoryNet",))
    receivables = _annual_instant_series(nvda, ("AccountsReceivableNetCurrent",))
    if not inventory.empty:
        metrics["nvda_inventory_growth"] = inventory.pct_change(fill_method=None) * 100
    if not receivables.empty:
        metrics["nvda_receivables_growth"] = receivables.pct_change(fill_method=None) * 100
    return {key: clean_series(value) for key, value in metrics.items()}, pd.DataFrame(company_rows), failures


SEC_METRIC_META: dict[str, dict[str, Any]] = {
    "hyperscaler_capex": {"name": "Hyperscaler capex · annual", "unit": "$bn", "direction": "high", "weight": 1.1, "why": "Cash infrastructure spending by Microsoft, Alphabet, Meta, Amazon and Oracle, aggregated from annual SEC facts."},
    "capex_growth": {"name": "Hyperscaler capex growth", "unit": "% YoY", "direction": "high", "weight": 1.2, "why": "Acceleration tests how quickly the capital cycle is expanding."},
    "capex_to_ocf": {"name": "Hyperscaler capex / operating cash flow", "unit": "%", "direction": "high", "weight": 1.3, "why": "Shows how much internally generated cash is absorbed by infrastructure."},
    "capex_to_revenue": {"name": "Hyperscaler capex / revenue", "unit": "%", "direction": "high", "weight": 1.0, "why": "Compares infrastructure intensity with the revenue base funding it."},
    "nvda_inventory_growth": {"name": "NVIDIA inventory growth", "unit": "% YoY", "direction": "high", "weight": 0.9, "why": "A sharp inventory build can flag supply outrunning realized demand, though product ramps also raise inventory."},
    "nvda_receivables_growth": {"name": "NVIDIA receivables growth", "unit": "% YoY", "direction": "high", "weight": 0.9, "why": "Receivables growing unusually fast can signal looser terms or customer concentration risk."},
}


def build_sec_snapshots(series_by_key: dict[str, pd.Series]) -> list[MetricSnapshot]:
    metrics: list[MetricSnapshot] = []
    for key, meta in SEC_METRIC_META.items():
        history = clean_series(series_by_key.get(key, pd.Series(dtype=float)))
        if history.empty:
            continue
        value = float(history.iloc[-1])
        percentile = percentile_rank(history, value)
        direction = str(meta["direction"])
        metrics.append(
            MetricSnapshot(
                key=key,
                name=str(meta["name"]),
                category="AI capital cycle",
                value=value,
                unit=str(meta["unit"]),
                as_of=history.index[-1],
                risk_score=risk_from_percentile(percentile, direction),
                percentile=percentile,
                direction=direction,
                weight=float(meta["weight"]),
                change=float(history.iloc[-1] - history.iloc[-2]) if len(history) > 1 else None,
                history=history,
                why=str(meta["why"]),
                watch="Annual SEC facts are audited but lag markets; fiscal year-ends differ by company.",
                source_name="SEC company facts",
                source_url="https://www.sec.gov/edgar/sec-api-documentation",
                frequency="Annual",
            )
        )
    return metrics
