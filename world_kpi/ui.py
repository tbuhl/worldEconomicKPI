from __future__ import annotations

import html
from typing import Iterable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from world_kpi.scoring import MetricSnapshot, risk_label


COLORS = {
    "Calm": "#57e3b2",
    "Watch": "#f4c95d",
    "Elevated": "#fb923c",
    "Severe": "#fb7185",
    "Unavailable": "#64748b",
}

RECESSIONS = (
    ("1990-07-01", "1991-03-31"),
    ("2001-03-01", "2001-11-30"),
    ("2007-12-01", "2009-06-30"),
    ("2020-02-01", "2020-04-30"),
)

CRISIS_MARKERS = (
    ("2000-03-24", "Dot-com peak", "#a78bfa"),
    ("2007-10-09", "GFC build-up", "#fb923c"),
    ("2008-09-15", "Lehman", "#fb7185"),
)


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root { --bg:#07111f; --panel:#0d1a2b; --line:rgba(148,163,184,.16); --ink:#f8fafc; --muted:#94a3b8; --mint:#57e3b2; }
        .stApp { background: radial-gradient(circle at 75% -10%, rgba(56,189,248,.10), transparent 31rem), #07111f; color:var(--ink); }
        [data-testid="stHeader"] { background:rgba(7,17,31,.85); }
        [data-testid="stSidebar"] { background:#081524; border-right:1px solid var(--line); }
        [data-testid="stSidebar"] h3 { color:#f1f5f9!important; }
        [data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] .stCaption { color:#8fa2b8!important; }
        .block-container { max-width:1450px; padding-top:1.7rem; padding-bottom:4rem; }
        h1,h2,h3 { letter-spacing:-.025em; }
        h1 { font-size:clamp(2.4rem,5vw,4.5rem)!important; line-height:.98!important; font-weight:650!important; }
        h2 { font-size:1.7rem!important; margin-top:2.2rem!important; }
        .eyebrow { color:var(--mint); text-transform:uppercase; letter-spacing:.18em; font-size:.72rem; font-weight:750; margin-bottom:.8rem; }
        .hero { padding:2.2rem 0 1.3rem; }
        .hero p { color:#aebdd0; max-width:850px; font-size:1.08rem; line-height:1.65; }
        .metric-card { min-height:145px; background:linear-gradient(145deg,rgba(18,36,57,.97),rgba(11,26,43,.97)); border:1px solid var(--line); border-radius:18px; padding:1.05rem 1.15rem; box-shadow:0 14px 36px rgba(0,0,0,.18); }
        .metric-label { color:#94a3b8; font-size:.73rem; letter-spacing:.06em; text-transform:uppercase; min-height:2.1em; }
        .metric-value { color:#f8fafc; font-size:1.7rem; letter-spacing:-.035em; margin:.35rem 0 .25rem; font-weight:680; white-space:nowrap; }
        .metric-meta { color:#8fa2b8; font-size:.74rem; }
        .risk-pill { display:inline-flex; align-items:center; gap:.35rem; margin-top:.55rem; padding:.24rem .5rem; border-radius:999px; font-size:.68rem; font-weight:750; letter-spacing:.04em; text-transform:uppercase; border:1px solid currentColor; }
        .section-note { color:#94a3b8; font-size:.9rem; margin-top:-.6rem; margin-bottom:1.1rem; }
        .callout { background:rgba(87,227,178,.07); border:1px solid rgba(87,227,178,.22); border-radius:18px; padding:1.15rem 1.3rem; color:#d6e3ee; line-height:1.55; }
        .callout strong { color:#fff; }
        .signal-row { border-left:3px solid var(--signal); background:rgba(15,31,50,.72); padding:.85rem 1rem; border-radius:0 12px 12px 0; margin:.55rem 0; }
        .signal-row .title { font-weight:700; color:#f1f5f9; }
        .signal-row .copy { color:#94a3b8; font-size:.84rem; margin-top:.25rem; }
        .tiny { color:#71849b; font-size:.72rem; }
        div[data-testid="stTabs"] button { color:#94a3b8; }
        div[data-testid="stTabs"] button[aria-selected="true"] { color:#f8fafc; }
        div[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:14px; overflow:hidden; }
        .stPlotlyChart { background:rgba(11,26,43,.50); border:1px solid var(--line); border-radius:18px; padding:.3rem; }
        .stButton button { border-radius:12px; border:1px solid rgba(87,227,178,.35); color:#dffcf3; background:rgba(87,227,178,.08); }
        .stButton button:hover { border-color:#57e3b2; color:#fff; }
        a { color:#68d7ff!important; }
        @media(max-width:800px) {
          .block-container{width:100%!important;max-width:100%!important;padding-left:1rem!important;padding-right:1rem!important;overflow:hidden}
          .hero,.hero p{width:100%!important;max-width:100%!important;overflow-wrap:anywhere}
          .metric-card{min-height:125px}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def format_value(value: float, unit: str) -> str:
    if pd.isna(value):
        return "—"
    if unit == "$tn":
        return f"${value:,.2f}tn"
    if unit == "$bn":
        return f"${value:,.0f}bn"
    if unit in {"%", "% YoY", "% ann.", "% net", "% GDP"}:
        return f"{value:,.1f}%"
    if unit == "pp":
        return f"{value:,.2f} pp"
    if unit == "% ann.":
        return f"{value:,.1f}%"
    if unit in {"index", "z-score"}:
        return f"{value:,.2f}"
    return f"{value:,.2f} {unit}".strip()


def metric_card(label: str, value: str, meta: str, score: float | None = None) -> None:
    state = risk_label(score) if score is not None else "Unavailable"
    pill = ""
    if score is not None and not pd.isna(score):
        pill = f'<span class="risk-pill" style="color:{COLORS[state]}">{state} · {score:.0f}/100</span>'
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-label">{html.escape(label)}</div>
          <div class="metric-value">{html.escape(value)}</div>
          <div class="metric-meta">{html.escape(meta)}</div>
          {pill}
        </div>
        """,
        unsafe_allow_html=True,
    )


def base_layout(figure: go.Figure, *, height: int = 390, y_title: str = "") -> go.Figure:
    figure.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Arial", color="#aebdd0", size=12),
        margin=dict(l=20, r=20, t=42, b=20),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=0),
        xaxis=dict(gridcolor="rgba(148,163,184,.08)", zeroline=False),
        yaxis=dict(gridcolor="rgba(148,163,184,.10)", zeroline=False, title=y_title),
    )
    return figure


def line_chart(
    series: pd.Series,
    title: str,
    unit: str,
    years: int | None = None,
    *,
    recession_bands: bool = True,
) -> go.Figure:
    series = series.dropna().sort_index()
    if years and not series.empty:
        series = series.loc[series.index >= series.index.max() - pd.DateOffset(years=years)]
    figure = go.Figure(
        go.Scatter(
            x=series.index,
            y=series.values,
            mode="lines",
            line=dict(color="#57e3b2", width=2.2),
            fill="tozeroy" if unit == "z-score" else None,
            fillcolor="rgba(87,227,178,.07)",
            name=title,
        )
    )
    if recession_bands:
        for start, end in RECESSIONS:
            figure.add_vrect(
                x0=start,
                x1=end,
                fillcolor="rgba(148,163,184,.10)",
                line_width=0,
                layer="below",
            )
        for marker_number, (date, label, color) in enumerate(CRISIS_MARKERS):
            marker_date = pd.Timestamp(date)
            if not series.empty and series.index.min() <= marker_date <= series.index.max():
                # Plotly's add_vline annotation helper performs unsupported arithmetic on
                # Pandas timestamps in recent Pandas versions, so keep line and label explicit.
                figure.add_shape(
                    type="line",
                    x0=date,
                    x1=date,
                    y0=0,
                    y1=1,
                    xref="x",
                    yref="paper",
                    line=dict(width=1.2, dash="dot", color=color),
                    layer="above",
                )
                figure.add_annotation(
                    x=date,
                    y=1.02 + (marker_number % 2) * 0.07,
                    xref="x",
                    yref="paper",
                    text=label,
                    showarrow=False,
                    xanchor="left",
                    font=dict(size=10, color=color),
                )
    figure.update_layout(title=dict(text=title, x=0.02, font=dict(size=16, color="#f1f5f9")))
    return base_layout(figure, y_title=unit)


def multi_line_chart(
    frame: pd.DataFrame,
    title: str,
    unit: str,
    years: int | None = None,
) -> go.Figure:
    """Plot a compact comparison of several aligned time series."""
    frame = frame.copy().sort_index().dropna(how="all")
    if years and not frame.empty:
        frame = frame.loc[frame.index >= frame.index.max() - pd.DateOffset(years=years)]
    palette = ("#57e3b2", "#68d7ff", "#a78bfa", "#f4c95d", "#fb923c", "#fb7185")
    figure = go.Figure()
    for index, column in enumerate(frame.columns):
        figure.add_trace(
            go.Scatter(
                x=frame.index,
                y=frame[column],
                mode="lines",
                name=str(column),
                line=dict(color=palette[index % len(palette)], width=2.1),
            )
        )
    figure.update_layout(title=dict(text=title, x=0.02, font=dict(size=16, color="#f1f5f9")))
    return base_layout(figure, height=430, y_title=unit)


def treasury_flow_bar(summary: pd.DataFrame) -> go.Figure:
    """Show the latest reported monthly Treasury flow for the current top holders."""
    frame = summary.sort_values("Latest net flow ($bn)").copy()
    values = frame["Latest net flow ($bn)"]
    colors = ["#57e3b2" if value >= 0 else "#fb7185" for value in values]
    labels = [f"{value:+.1f}" for value in values]
    figure = go.Figure(
        go.Bar(
            x=values,
            y=frame["Country"],
            orientation="h",
            marker_color=colors,
            text=labels,
            textposition="outside",
            cliponaxis=False,
            customdata=frame[["Assessment", "Sale percentile"]],
            hovertemplate=(
                "%{y}<br>Net flow: $%{x:.1f}bn"
                "<br>%{customdata[0]} · sale percentile %{customdata[1]:.0f}<extra></extra>"
            ),
        )
    )
    figure.add_vline(x=0, line_width=1, line_color="rgba(226,232,240,.45)")
    figure.update_layout(
        title=dict(
            text="Latest monthly net Treasury flow",
            x=0.02,
            font=dict(size=16, color="#f1f5f9"),
        )
    )
    figure = base_layout(figure, height=390)
    figure.update_xaxes(title="$bn · buying (+) / selling (−)")
    return figure


def category_bar(scores: dict[str, float]) -> go.Figure:
    frame = pd.DataFrame({"pillar": scores.keys(), "score": scores.values()}).sort_values("score")
    frame["state"] = frame["score"].map(risk_label)
    figure = go.Figure(
        go.Bar(
            x=frame["score"],
            y=frame["pillar"],
            orientation="h",
            marker_color=[COLORS[state] for state in frame["state"]],
            text=[f"{score:.0f}" for score in frame["score"]],
            textposition="outside",
            cliponaxis=False,
        )
    )
    figure.update_xaxes(range=[0, 105], title="Historical pressure percentile")
    return base_layout(figure, height=380)


def crisis_heatmap(frame: pd.DataFrame) -> go.Figure:
    if frame.empty:
        return go.Figure()
    pivot = frame.pivot(index="category", columns="period", values="score")
    period_order = [period for period in ("Dot-com peak", "GFC build-up", "Lehman", "Now") if period in pivot.columns]
    pivot = pivot.reindex(columns=period_order)
    figure = px.imshow(
        pivot,
        aspect="auto",
        text_auto=".0f",
        color_continuous_scale=[
            [0, "#123a38"],
            [0.5, "#6b5f28"],
            [0.7, "#8a4928"],
            [1, "#7f3044"],
        ],
        zmin=0,
        zmax=100,
    )
    figure.update_coloraxes(showscale=False)
    figure.update_layout(title=dict(text="Same dashboard lens, different moments", x=0.02, font=dict(size=16, color="#f1f5f9")))
    return base_layout(figure, height=430)


def risk_table(metrics: Iterable[MetricSnapshot]) -> pd.DataFrame:
    rows = []
    for metric in metrics:
        rows.append(
            {
                "KPI": metric.name,
                "Pillar": metric.category,
                "Latest": format_value(metric.value, metric.unit),
                "Risk": metric.state,
                "Score": round(metric.risk_score),
                "Historical percentile": round(metric.percentile),
                "As of": metric.as_of.strftime("%Y-%m-%d"),
                "Frequency": metric.frequency,
                "Source": metric.source_name,
            }
        )
    return pd.DataFrame(rows)


def signal_rows(metrics: Iterable[MetricSnapshot], limit: int = 6) -> None:
    ranked = sorted(metrics, key=lambda item: item.risk_score if not pd.isna(item.risk_score) else -1, reverse=True)[:limit]
    for metric in ranked:
        color = COLORS[metric.state]
        copy = f"{format_value(metric.value, metric.unit)} · {metric.percentile:.0f}th historical percentile · data through {metric.as_of:%d %b %Y}"
        st.markdown(
            f'<div class="signal-row" style="--signal:{color}"><div class="title">{html.escape(metric.name)}</div><div class="copy">{html.escape(copy)}</div></div>',
            unsafe_allow_html=True,
        )
