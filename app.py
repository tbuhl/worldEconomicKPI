from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os

import numpy as np
import pandas as pd
import streamlit as st

from world_kpi.ai_loop import AI_RELATIONSHIPS, AI_NEWS, ai_loop_figure
from world_kpi.data import (
    CACHE_DIR,
    build_fred_snapshots,
    build_market_snapshots,
    build_sec_snapshots,
    hydrate_seed_cache,
    reset_source_health,
    source_health,
    load_daily_debt,
    load_fred_bundle,
    load_market_metrics,
    load_sec_ai_metrics,
    load_tic_holdings,
    summarize_top_tic_holders,
)
from world_kpi.scoring import (
    MetricSnapshot,
    category_scores,
    describe_metric,
    historical_category_scores,
    overall_pressure,
    percentile_rank,
    risk_from_percentile,
    risk_label,
)
from world_kpi.ui import (
    category_bar,
    crisis_heatmap,
    format_value,
    inject_css,
    line_chart,
    metric_card,
    multi_line_chart,
    risk_table,
    signal_rows,
    treasury_flow_bar,
)


st.set_page_config(
    page_title="World KPI Radar",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="auto",
)
inject_css()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_dashboard_data() -> dict:
    # Each provider can fail independently; one outage should not blank the full dashboard.
    reset_source_health()
    hydrate_seed_cache()
    with ThreadPoolExecutor(max_workers=5) as executor:
        fred_job = executor.submit(load_fred_bundle)
        market_job = executor.submit(load_market_metrics)
        sec_job = executor.submit(load_sec_ai_metrics)
        debt_job = executor.submit(load_daily_debt)
        tic_job = executor.submit(load_tic_holdings)

        try:
            fred_series, fred_failures = fred_job.result()
        except Exception as exc:
            fred_series, fred_failures = {}, {"fred_provider": str(exc)}
        try:
            market_series, market_failures = market_job.result()
        except Exception as exc:
            market_series, market_failures = {}, {"market_provider": str(exc)}
        try:
            sec_series, company_capex, sec_failures = sec_job.result()
        except Exception as exc:
            sec_series, company_capex, sec_failures = {}, pd.DataFrame(), {"sec_provider": str(exc)}
        try:
            debt = debt_job.result()
        except Exception as exc:
            debt = pd.Series(dtype=float)
            fred_failures["daily_debt"] = str(exc)
        try:
            tic = tic_job.result()
        except Exception as exc:
            tic = pd.DataFrame()
            fred_failures["tic_holdings"] = str(exc)

    metrics = (
        build_fred_snapshots(fred_series)
        + build_market_snapshots(market_series)
        + build_sec_snapshots(sec_series)
    )

    tic_summary = summarize_top_tic_holders(tic)
    if not tic_summary.empty:
        top_countries = tic_summary["Country"].tolist()
        top_flows = (
            tic.loc[tic["country"].isin(top_countries)]
            .pivot_table(index="date", columns="country", values="for_treas_net", aggfunc="last")
            .sum(axis=1, min_count=len(top_countries))
            .dropna()
        )
        if not top_flows.empty:
            value = float(top_flows.iloc[-1])
            pct = percentile_rank(top_flows, value)
            metrics.append(
                MetricSnapshot(
                    key="top5_treasury_flow",
                    name="Top-five foreign-holder Treasury flow",
                    category="Sovereign & rates",
                    value=value,
                    unit="$bn",
                    as_of=top_flows.index[-1],
                    risk_score=risk_from_percentile(pct, "low"),
                    percentile=pct,
                    direction="low",
                    weight=1.0,
                    change=float(top_flows.iloc[-1] - top_flows.iloc[-2]) if len(top_flows) > 1 else None,
                    history=top_flows,
                    why="Aggregates reported monthly net Treasury buying or selling by the five largest current foreign country holders.",
                    watch="The top-five membership is based on the latest month. TIC is custody-based, monthly and revised; negative values mean reported net selling, not necessarily forced liquidation.",
                    source_name="U.S. Treasury TIC",
                    source_url="https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table3.txt",
                    frequency="Monthly",
                )
            )

    return {
        "metrics": metrics,
        "debt": debt,
        "tic": tic,
        "tic_summary": tic_summary,
        "company_capex": company_capex,
        "failures": {**fred_failures, **market_failures, **sec_failures},
        "loaded_at": datetime.now(timezone.utc),
        "source_health": source_health(),
    }


def force_source_refresh() -> None:
    # Mark source files stale without deleting the persistent history archives. Incremental
    # providers will merge a recent overlap; other providers replace their smaller snapshots.
    if CACHE_DIR.exists():
        for path in CACHE_DIR.rglob("*"):
            if path.is_file():
                try:
                    os.utime(path, (1, 1))
                except OSError:
                    pass
    st.cache_data.clear()


def metric_by_key(metrics: list[MetricSnapshot], key: str) -> MetricSnapshot | None:
    return next((metric for metric in metrics if metric.key == key), None)


def format_signed_billions(value: float) -> str:
    if pd.isna(value):
        return "—"
    sign = "+" if value >= 0 else "−"
    return f"{sign}${abs(value):,.1f}bn"


def render_explorer(
    metrics: list[MetricSnapshot],
    categories: str | tuple[str, ...],
    lookback: int | None,
    key: str,
) -> None:
    categories = (categories,) if isinstance(categories, str) else categories
    options = [metric for metric in metrics if metric.category in categories]
    if not options:
        st.info("No live series from this section is available right now.")
        return
    selected_name = st.selectbox(
        "Inspect an indicator",
        [metric.name for metric in options],
        key=f"indicator_{key}",
    )
    selected = next(metric for metric in options if metric.name == selected_name)
    chart_col, note_col = st.columns([1.65, 1], gap="large")
    with chart_col:
        st.plotly_chart(
            line_chart(selected.history, selected.name, selected.unit, lookback),
            width="stretch",
            key=f"chart_{key}_{selected.key}",
        )
    with note_col:
        metric_card(
            selected.name,
            format_value(selected.value, selected.unit),
            f"{selected.frequency} · {selected.as_of:%d %b %Y}",
            selected.risk_score,
        )
        st.markdown(f"<div class='callout' style='margin-top:.8rem'>{describe_metric(selected)}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<p class='tiny'>History available: {selected.history.index[0]:%Y}–{selected.history.index[-1]:%Y}<br>Watch: {selected.watch}<br>Source: <a href='{selected.source_url}' target='_blank'>{selected.source_name}</a></p>",
            unsafe_allow_html=True,
        )
    section_frame = risk_table(options).sort_values("Score", ascending=False)
    st.dataframe(
        section_frame,
        width="stretch",
        hide_index=True,
        height=min(460, 37 * (len(section_frame) + 1)),
        column_config={
            "Score": st.column_config.ProgressColumn("Risk score", min_value=0, max_value=100),
        },
    )


with st.sidebar:
    st.markdown("<div class='eyebrow'>Control room</div>", unsafe_allow_html=True)
    st.markdown("### World KPI Radar")
    st.caption("Daily market signals + latest official macro releases")
    st.caption("Build 2026-11-22 · refresh diagnostics + IPO update")
    history_window = st.selectbox(
        "History window",
        ("Since 1990 · recommended", "20 years", "10 years", "5 years"),
    )
    lookback_years = {
        "Since 1990 · recommended": None,
        "20 years": 20,
        "10 years": 10,
        "5 years": 5,
    }[history_window]
    st.markdown("---")
    refresh = st.button("↻ Refresh all sources", width="stretch")
    if refresh:
        force_source_refresh()
        st.rerun()
    st.markdown(
        "<p class='tiny'>Historical archives are retained. Refresh downloads only a recent overlap for incremental feeds, then merges revisions and new observations.</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**Interpretation rule**")
    st.caption("Scores show where a reading sits in its own history. They are neither a crash probability nor investment advice.")


with st.spinner("Connecting the economic, Treasury, market and filing data…"):
    data = load_dashboard_data()

metrics: list[MetricSnapshot] = data["metrics"]
if not metrics:
    st.error("No source returned usable data. Check the network connection and try Refresh all sources.")
    st.stop()

scores = category_scores(metrics)
pressure = overall_pressure(scores)
as_of = max(metric.as_of for metric in metrics)
loaded_at = data["loaded_at"]
health = pd.DataFrame(data["source_health"])
if not health.empty:
    fallback_count = int(health["Status"].isin(["Fallback", "Unavailable"]).sum())
    downloads = int(health["Status"].eq("Downloaded").sum())
    if fallback_count:
        st.warning(
            f"{fallback_count} source downloads failed; saved history is shown where available. "
            f"{downloads} sources downloaded successfully. See Source health in the KPI library."
        )
    st.caption(
        f"Last data check: {loaded_at:%d %b %Y %H:%M} UTC · "
        f"{downloads} downloaded · {int(health['Status'].eq('Cached').sum())} cached · "
        f"{fallback_count} failed. Each KPI shows its own observation date."
    )

st.markdown(
    f"""
    <div class="hero">
      <div class="eyebrow">Global macro • sovereign risk • AI capital cycle</div>
      <h1>World KPI<br>Radar</h1>
      <p>A historically calibrated early-warning dashboard for economic vulnerability and live market stress. It tracks {len(metrics)} signals across {len(scores)} pillars—then shows where today resembles, and differs from, the dot-com peak and the global financial crisis.</p>
      <div class="tiny">Latest observation in the dashboard: {as_of:%d %B %Y} · checked {loaded_at:%d %b %Y %H:%M} UTC</div>
    </div>
    """,
    unsafe_allow_html=True,
)

overview_tab, macro_tab, sovereign_tab, credit_tab, markets_tab, loop_tab, library_tab = st.tabs(
    [
        "Overview",
        "Macro & policy",
        "Sovereign & rates",
        "Credit & plumbing",
        "Markets & AI",
        "AI capital loop",
        "KPI library",
    ]
)

with overview_tab:
    debt: pd.Series = data["debt"]
    tic: pd.DataFrame = data["tic"]
    tic_summary: pd.DataFrame = data["tic_summary"]
    top5_metric = metric_by_key(metrics, "top5_treasury_flow")
    top5_flow = top5_metric.value if top5_metric else np.nan
    top5_sellers = (
        int((tic_summary["Latest net flow ($bn)"] < 0).sum()) if not tic_summary.empty else 0
    )
    seller_rows = (
        tic_summary.loc[tic_summary["Latest net flow ($bn)"] < 0]
        .sort_values("Latest net flow ($bn)")
        if not tic_summary.empty
        else pd.DataFrame()
    )
    largest_seller = seller_rows.iloc[0] if not seller_rows.empty else None
    top5_meta = (
        f"{top5_sellers} of 5 sellers · largest: {largest_seller['Country']}"
        if largest_seller is not None
        else "No net sellers in latest TIC month"
    )
    debt_latest = float(debt.iloc[-1]) if not debt.empty else np.nan
    debt_1y = float(debt.pct_change(252, fill_method=None).dropna().iloc[-1] * 100) if len(debt) > 252 else np.nan
    ai_score = scores.get("AI capital cycle", np.nan)
    credit_score = scores.get("Credit & plumbing", np.nan)

    top_cols = st.columns(5, gap="small")
    with top_cols[0]:
        metric_card("Broad pressure index", f"{pressure:.0f} / 100", f"{risk_label(pressure)} · equal-weight pillars", pressure)
    with top_cols[1]:
        metric_card("Credit stress", f"{credit_score:.0f} / 100" if not pd.isna(credit_score) else "—", "Market + bank plumbing", credit_score)
    with top_cols[2]:
        metric_card("AI capital cycle", f"{ai_score:.0f} / 100" if not pd.isna(ai_score) else "—", "Capex + crowding + balance sheets", ai_score)
    with top_cols[3]:
        metric_card("U.S. public debt", format_value(debt_latest, "$tn"), f"{debt_1y:+.1f}% approx. 1y" if not pd.isna(debt_1y) else "Daily Treasury data")
    with top_cols[4]:
        metric_card(
            "Top-5 foreign-holder flow",
            format_signed_billions(top5_flow),
            top5_meta,
            top5_metric.risk_score if top5_metric else None,
        )

    st.markdown("## What the dashboard says now")
    highest = max(scores, key=scores.get)
    lowest = min(scores, key=scores.get)
    credit_copy = (
        "Acute credit stress is elevated, so transmission risk deserves close attention."
        if credit_score >= 70
        else "Acute credit plumbing is not yet in its most stressed historical tail."
    )
    st.markdown(
        f"<div class='callout'><strong>{risk_label(pressure)} broad pressure ({pressure:.0f}/100).</strong> The most stretched pillar is <strong>{highest}</strong> at {scores[highest]:.0f}/100, while <strong>{lowest}</strong> is least stretched at {scores[lowest]:.0f}/100. {credit_copy} This mix is better read as a map of fragilities than as a forecast date.</div>",
        unsafe_allow_html=True,
    )

    chart_col, signals_col = st.columns([1.35, 1], gap="large")
    with chart_col:
        st.markdown("## Pressure by pillar")
        st.markdown("<p class='section-note'>Equal-weight pillar scores prevent the largest data category from dominating.</p>", unsafe_allow_html=True)
        st.plotly_chart(category_bar(scores), width="stretch", key="overview_pillars")
    with signals_col:
        st.markdown("## Signals furthest from normal")
        st.markdown("<p class='section-note'>High risk score means historically unusual in the adverse direction.</p>", unsafe_allow_html=True)
        signal_rows(metrics, 7)

    st.markdown("## Then versus now")
    st.markdown(
        "<p class='section-note'>Each cell replays the available indicators at that date through the same percentile lens. This is a revised-data comparison—not a point-in-time backtest.</p>",
        unsafe_allow_html=True,
    )
    crisis_frame = historical_category_scores(
        metrics,
        {
            "Dot-com peak": "2000-03-24",
            "GFC build-up": "2007-10-09",
            "Lehman": "2008-09-15",
            "Now": as_of,
        },
    )
    st.plotly_chart(crisis_heatmap(crisis_frame), width="stretch", key="crisis_heatmap")
    st.markdown(
        """
        <div class="callout"><strong>The pattern matters more than the average.</strong> The dot-com episode was primarily an equity valuation and technology-capital cycle. The GFC combined housing credit, leverage, funding fragility and then acute market stress. Today can share expensive assets or concentrated capex without sharing 2008's mortgage underwriting and bank-capital structure. A true systemic warning would be broadening: weak growth + widening credit spreads + tighter bank lending + impaired funding markets.</div>
        """,
        unsafe_allow_html=True,
    )

with macro_tab:
    st.markdown("## Macro & policy")
    st.markdown("<p class='section-note'>The growth engine, labour market and the inflation constraint on policy support.</p>", unsafe_allow_html=True)
    render_explorer(metrics, ("Growth & labour", "Inflation & policy"), lookback_years, "macro")

with sovereign_tab:
    st.markdown("## Sovereign debt & the global rate anchor")
    st.markdown("<p class='section-note'>Debt sustainability is a flow problem as much as a stock problem: refinancing rates, interest expense, currency demand and investor capacity interact.</p>", unsafe_allow_html=True)
    tic_summary = data["tic_summary"]
    top_countries = tic_summary["Country"].tolist() if not tic_summary.empty else []
    if not data["debt"].empty or top_countries:
        debt_col, holdings_col = st.columns(2, gap="large")
        with debt_col:
            if not data["debt"].empty:
                st.plotly_chart(line_chart(data["debt"], "U.S. total public debt outstanding", "$tn", lookback_years, recession_bands=False), width="stretch", key="debt_chart")
        with holdings_col:
            if top_countries:
                holdings = (
                    data["tic"].loc[data["tic"]["country"].isin(top_countries)]
                    .pivot_table(index="date", columns="country", values="for_treas_pos", aggfunc="last")
                    .reindex(columns=top_countries)
                )
                st.plotly_chart(
                    multi_line_chart(holdings, "Top five foreign holders of U.S. Treasuries", "$bn", lookback_years),
                    width="stretch",
                    key="top5_holdings_chart",
                )

    if not tic_summary.empty:
        st.markdown("## Who is buying, who is selling?")
        st.markdown(
            "<p class='section-note'>The largest five countries are selected from the latest holdings month. Negative flow is reported net selling; the percentile compares that sale with the same country's monthly history.</p>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(treasury_flow_bar(tic_summary), width="stretch", key="top5_flow_chart")
        display_tic = tic_summary.copy()
        display_tic["As of"] = pd.to_datetime(display_tic["As of"]).dt.strftime("%Y-%m")
        st.dataframe(
            display_tic,
            width="stretch",
            hide_index=True,
            column_config={
                "Holdings ($bn)": st.column_config.NumberColumn(format="$%.1f"),
                "Holdings change ($bn)": st.column_config.NumberColumn(format="$%+.1f"),
                "Latest net flow ($bn)": st.column_config.NumberColumn(format="$%+.1f"),
                "3m net flow ($bn)": st.column_config.NumberColumn(format="$%+.1f"),
                "12m holdings change (%)": st.column_config.NumberColumn(format="%+.1f%%"),
                "Sale percentile": st.column_config.ProgressColumn(
                    "Sale abnormality", min_value=0, max_value=100, format="%.0f"
                ),
            },
        )

        sellers = tic_summary.loc[tic_summary["Latest net flow ($bn)"] < 0].sort_values(
            "Latest net flow ($bn)"
        )
        aggregate_flow = float(tic_summary["Latest net flow ($bn)"].sum())
        if not sellers.empty:
            largest = sellers.iloc[0]
            flow_copy = (
                f"<strong>{largest['Country']} was the largest seller among the current top five</strong>, "
                f"with {format_signed_billions(float(largest['Latest net flow ($bn)']))} of reported net flow. "
                f"That sale ranks at the {largest['Sale percentile']:.0f}th percentile of its available monthly history "
                f"and is classified as <strong>{str(largest['Assessment']).lower()}</strong>. "
            )
        else:
            flow_copy = "<strong>None of the current top five was a net seller in the latest month.</strong> "
        st.markdown(
            f"<div class='callout'>{flow_copy}Together the five reported {format_signed_billions(aggregate_flow)}. "
            "TIC is custody-based, monthly and revised. Holdings changes combine transactions, valuation effects and custody shifts, so they need not equal the net-flow column. The current country table begins in 2020.</div>",
            unsafe_allow_html=True,
        )
    render_explorer(metrics, "Sovereign & rates", lookback_years, "sovereign")

with credit_tab:
    st.markdown("## Credit & financial plumbing")
    st.markdown("<p class='section-note'>These signals answer the crucial question: are vulnerabilities turning into a self-reinforcing financing shock?</p>", unsafe_allow_html=True)
    render_explorer(metrics, "Credit & plumbing", lookback_years, "credit")
    st.markdown(
        "<div class='callout'><strong>2008 checklist.</strong> Look for simultaneous high-yield and investment-grade spread widening, positive financial-stress indexes, aggressive bank tightening, and rising delinquencies. One isolated red light is less persuasive than breadth across the chain.</div>",
        unsafe_allow_html=True,
    )

with markets_tab:
    st.markdown("## Markets & the AI capital cycle")
    st.markdown("<p class='section-note'>A price-based crowding lens is combined with cash capex, cash generation and supplier balance-sheet signals from SEC filings.</p>", unsafe_allow_html=True)
    render_explorer(metrics, ("Markets & global", "AI capital cycle"), lookback_years, "markets_ai")
    company_capex: pd.DataFrame = data["company_capex"]
    if not company_capex.empty:
        st.markdown("### Infrastructure intensity by company")
        display_capex = company_capex.sort_values("Capex · latest FY ($bn)", ascending=False).copy()
        display_capex["Filed through"] = pd.to_datetime(display_capex["Filed through"]).dt.strftime("%Y-%m-%d")
        st.dataframe(
            display_capex,
            width="stretch",
            hide_index=True,
            column_config={
                "Capex · latest FY ($bn)": st.column_config.NumberColumn(format="$%.1fbn"),
                "Capex growth": st.column_config.NumberColumn(format="%.1f%%"),
                "Capex / operating cash flow": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
        st.caption("Fiscal year-ends differ. Amazon equipment acquired under finance leases may not be fully captured by cash PP&E facts, so cross-company comparison is directional.")

with loop_tab:
    st.markdown("## The AI capital loop")
    st.caption("News reviewed 22 November 2026 · dated announcements below are maintained separately from live KPI feeds.")
    for news in AI_NEWS:
        with st.expander(f"{news['date']} · {news['title']}", expanded=True):
            st.markdown(news["facts"])
            st.markdown(f"**Interpretation:** {news['interpretation']}")
            st.markdown(f"[Company announcement]({news['source']})")
    st.markdown(
        "<p class='section-note'>Capital can flow from a vendor or cloud provider into a model company and return as chip or compute demand. That is not inherently fraudulent—but it can blur independent end demand and concentrate counterparty risk.</p>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(ai_loop_figure(), width="stretch", key="ai_sankey")
    st.markdown(
        """
        <div class="callout"><strong>What would validate the build-out?</strong> Durable outside revenue from enterprises and consumers, rising utilization, improving inference economics, and capex growth slowing toward operating-cash-flow growth. <strong>What would weaken it?</strong> Commitments repeatedly financed by counterparties inside the same loop, falling utilization or pricing, inventories and receivables outrunning sales, and debt-financed capex rising as credit spreads widen.</div>
        """,
        unsafe_allow_html=True,
    )
    relationship_display = AI_RELATIONSHIPS.rename(
        columns={
            "from": "Capital from",
            "to": "Capital / demand to",
            "magnitude": "Disclosed scale",
            "mechanism": "Feedback mechanism",
            "status": "Status",
            "as_of": "As of",
            "source": "Source",
        }
    )
    st.dataframe(
        relationship_display,
        width="stretch",
        hide_index=True,
        column_config={"Source": st.column_config.LinkColumn("Primary source", display_text="Open source")},
    )
    st.caption("Flow widths are illustrative and deliberately not dollar-scaled. Announced values mix investment, capacity, purchase commitments and conditional warrants and must not be summed.")

with library_tab:
    st.markdown("## KPI library & data dictionary")
    st.markdown("<p class='section-note'>Every live indicator, release date, historical position and provenance in one place.</p>", unsafe_allow_html=True)
    search = st.text_input("Search KPIs", placeholder="Try debt, unemployment, capex, spreads…")
    category_filter = st.multiselect("Pillars", sorted({metric.category for metric in metrics}))
    filtered = metrics
    if search:
        filtered = [metric for metric in filtered if search.lower() in f"{metric.name} {metric.why} {metric.category}".lower()]
    if category_filter:
        filtered = [metric for metric in filtered if metric.category in category_filter]
    library_frame = risk_table(filtered).sort_values(["Pillar", "Score"], ascending=[True, False])
    st.dataframe(
        library_frame,
        width="stretch",
        hide_index=True,
        height=620,
        column_config={"Score": st.column_config.ProgressColumn("Risk score", min_value=0, max_value=100)},
    )

    st.markdown("## Methodology")
    method_col, limitations_col = st.columns(2, gap="large")
    with method_col:
        st.markdown(
            """
            **1. Transform.** Levels are converted where appropriate to year-over-year growth.  
            **2. Calibrate.** The latest reading is ranked against its own available history, generally from 1990.  
            **3. Orient.** For some KPIs high is adverse; for growth and breadth low is adverse; two-sided shocks penalize either tail.  
            **4. Aggregate.** KPIs are weighted inside pillars, then pillars are equal-weighted.  
            **5. Compare.** Historical dates use the same lens, with only indicators available at that date.
            """
        )
    with limitations_col:
        st.markdown(
            """
            **Not a probability.** 80/100 means historically stretched, not an 80% crash chance.  
            **Revisions.** FRED history is today's revised history, not the vintage known at the time.  
            **Regime shifts.** Debt, inflation, regulation and market structure change across decades.  
            **Lags.** GDP, delinquency, TIC and SEC filing data arrive after the reference period.  
            **Licensing.** Data remain subject to each provider's terms; this app links to provenance.
            """
        )

    st.markdown("### Source health")
    if not health.empty:
        st.dataframe(health.sort_values(["Status", "Source"]), hide_index=True, width="stretch")
    failures = data["failures"]
    if failures:
        st.warning(f"{len(failures)} source series did not refresh. Cached or remaining sources are still displayed.")
        with st.expander("Show unavailable series"):
            st.json(failures)
    elif health.empty or not health["Status"].isin(["Fallback", "Unavailable"]).any():
        st.success("All configured source calls returned usable data in this refresh.")

st.markdown(
    "<p class='tiny' style='margin-top:3rem'>World KPI Radar · educational risk monitoring only · not investment, legal or tax advice.</p>",
    unsafe_allow_html=True,
)
