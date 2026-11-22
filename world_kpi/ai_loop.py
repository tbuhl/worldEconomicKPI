from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


AI_NEWS = [
    {
        "date": "2026-11-20",
        "title": "Anthropic IPO closes; supplier investors join private placement",
        "facts": (
            "Anthropic began Nasdaq trading on 19 November under **ANT**, priced at **$83**. "
            "The IPO closed with **$93.5bn gross proceeds**, including secondary shares; "
            "approximately **$91.6bn went to Anthropic** before fees. A concurrent "
            "**$26.0bn private placement** included AMD, Broadcom, Google, Micron, Microsoft, "
            "NVIDIA and TSMC Partners. The $119.5bn headline includes secondary proceeds."
        ),
        "interpretation": (
            "Public equity expands the funding base for compute spending. Supplier participation "
            "also increases links inside the AI capital loop. These are financing proceeds, "
            "not customer revenue or profit; compare subsequent cash burn and outside revenue "
            "with compute commitments. Individual supplier allocations were not disclosed here."
        ),
        "source": "https://www.anthropic.com/news/ipo-close",
    },
    {
        "date": "2026-11-17",
        "title": "NVIDIA Q3 FY2027: rapid growth, with working-capital exposure",
        "facts": (
            "NVIDIA reported **$115.8bn revenue (+103% YoY)** and **$107.6bn Data Center revenue "
            "(+110%)** for the quarter ended 25 October. GAAP gross margin was **74.8%**. "
            "Accounts receivable reached **$81.0bn**, versus $38.5bn at the fiscal year start; "
            "inventory was **$39.7bn**, versus $21.4bn. Q4 revenue guidance is **$130bn ±3%**, "
            "a forecast. The release also reports expanded Anthropic access to NVIDIA capacity."
        ),
        "interpretation": (
            "Strong revenue supports realized infrastructure demand. Receivables and inventory "
            "tie up cash and warrant comparison with sales, collections and product ramps. "
            "The balance-sheet changes above are year-to-date, not YoY; they do not by themselves "
            "establish customer distress. Guidance is separate from realized earnings."
        ),
        "source": "https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-third-quarter-fiscal-2027",
    },
]


# Announced values are not added together: they mix equity, warrants, purchase commitments,
# capacity targets and intended investment. The table exists to reveal feedback loops, not to
# manufacture a single headline total.
AI_RELATIONSHIPS = pd.DataFrame(
    [
        {
            "from": "Capital markets",
            "to": "Anthropic",
            "magnitude": "$91.6B issuer gross IPO proceeds",
            "mechanism": "New public equity funds operations and compute; excludes secondary proceeds",
            "status": "Closed",
            "as_of": "2026-11-20",
            "source": "https://www.anthropic.com/news/ipo-close",
        },
        {
            "from": "Supplier investor group",
            "to": "Anthropic",
            "magnitude": "$26B combined private placement",
            "mechanism": "AMD, Broadcom, Google, Micron, Microsoft, NVIDIA and TSMC Partners; individual allocations undisclosed",
            "status": "Closed",
            "as_of": "2026-11-20",
            "source": "https://www.anthropic.com/news/ipo-close",
        },
        {
            "from": "Capital markets",
            "to": "Hyperscalers",
            "magnitude": "Balance sheets + debt",
            "mechanism": "Debt/equity funds accelerated data-centre capex",
            "status": "Observed in filings",
            "as_of": "Rolling",
            "source": "https://www.sec.gov/edgar/sec-api-documentation",
        },
        {
            "from": "Amazon",
            "to": "Anthropic",
            "magnitude": "$5B now; up to $20B more",
            "mechanism": "Strategic investment tied to commercial milestones",
            "status": "Announced",
            "as_of": "2026",
            "source": "https://www.aboutamazon.com/news/company-news/amazon-invests-additional-5-billion-anthropic-ai",
        },
        {
            "from": "Anthropic",
            "to": "AWS / Trainium",
            "magnitude": ">$100B / 10 years",
            "mechanism": "Compute commitment returns demand to the investor's cloud",
            "status": "Commitment",
            "as_of": "2026",
            "source": "https://www.aboutamazon.com/news/company-news/amazon-invests-additional-5-billion-anthropic-ai",
        },
        {
            "from": "NVIDIA",
            "to": "OpenAI",
            "magnitude": "Up to $100B",
            "mechanism": "Progressive investment as each gigawatt is deployed",
            "status": "Letter of intent",
            "as_of": "2025-09-22",
            "source": "https://nvidianews.nvidia.com/news/openai-and-nvidia-announce-strategic-partnership-to-deploy-10gw-of-nvidia-systems",
        },
        {
            "from": "OpenAI",
            "to": "NVIDIA systems",
            "magnitude": "At least 10 GW",
            "mechanism": "GPU-system deployment creates vendor revenue",
            "status": "Letter of intent",
            "as_of": "2025-09-22",
            "source": "https://nvidianews.nvidia.com/news/openai-and-nvidia-announce-strategic-partnership-to-deploy-10gw-of-nvidia-systems",
        },
        {
            "from": "OpenAI",
            "to": "Oracle / Stargate",
            "magnitude": ">$300B+ / 5 years",
            "mechanism": "Cloud and data-centre capacity commitment",
            "status": "Announced partnership",
            "as_of": "2025-09-23",
            "source": "https://openai.com/index/five-new-stargate-sites/",
        },
        {
            "from": "SoftBank + partners",
            "to": "Stargate",
            "magnitude": "$500B intended / 4 years",
            "mechanism": "Equity and infrastructure capital for OpenAI compute",
            "status": "Intended investment",
            "as_of": "2025-01-21",
            "source": "https://openai.com/index/announcing-the-stargate-project/",
        },
        {
            "from": "OpenAI",
            "to": "AMD",
            "magnitude": "Up to 6 GW GPUs",
            "mechanism": "Purchase milestones unlock customer warrants",
            "status": "Multi-year agreement",
            "as_of": "2025-10",
            "source": "https://ir.amd.com/financial-information/sec-filings/content/0001193125-25-230895/0001193125-25-230895.pdf",
        },
        {
            "from": "AMD",
            "to": "OpenAI",
            "magnitude": "Warrant up to 160M shares",
            "mechanism": "$0.01 warrants vest with GPU purchases and milestones",
            "status": "Issued; conditional vesting",
            "as_of": "2025-10",
            "source": "https://ir.amd.com/financial-information/sec-filings/content/0001193125-25-230895/0001193125-25-230895.pdf",
        },
        {
            "from": "Enterprise customers",
            "to": "AI labs + clouds",
            "magnitude": "Revenue / usage",
            "mechanism": "The outside cash flow that ultimately validates the loop",
            "status": "Key validation variable",
            "as_of": "Rolling",
            "source": "https://www.sec.gov/edgar/search/",
        },
    ]
)


def ai_loop_figure() -> go.Figure:
    nodes = [
        "Capital markets",
        "Amazon",
        "NVIDIA",
        "AMD",
        "SoftBank + partners",
        "Hyperscalers",
        "Anthropic",
        "OpenAI",
        "Stargate",
        "AWS / Trainium",
        "NVIDIA systems",
        "Oracle / Stargate",
        "Enterprise customers",
        "Power + data centres",
        "Supplier investor group",
    ]
    node_index = {node: index for index, node in enumerate(nodes)}
    links = [
        ("Capital markets", "Hyperscalers", 6),
        ("Capital markets", "Anthropic", 4),
        ("Supplier investor group", "Anthropic", 3),
        ("Amazon", "Anthropic", 4),
        ("Anthropic", "AWS / Trainium", 6),
        ("NVIDIA", "OpenAI", 5),
        ("OpenAI", "NVIDIA systems", 5),
        ("AMD", "OpenAI", 3),
        ("OpenAI", "Oracle / Stargate", 7),
        ("SoftBank + partners", "Stargate", 7),
        ("Stargate", "Power + data centres", 7),
        ("Hyperscalers", "Power + data centres", 5),
        ("Enterprise customers", "Hyperscalers", 3),
        ("Enterprise customers", "Anthropic", 2),
        ("Enterprise customers", "OpenAI", 2),
    ]
    figure = go.Figure(
        go.Sankey(
            arrangement="snap",
            node={
                "pad": 18,
                "thickness": 16,
                "label": nodes,
                "color": ["#64748b", "#38bdf8", "#a78bfa", "#fb7185", "#fbbf24", "#38bdf8", "#8b5cf6", "#57e3b2", "#f4c95d", "#38bdf8", "#a78bfa", "#fb7185", "#e2e8f0", "#64748b", "#68d7ff"],
                "line": {"color": "rgba(255,255,255,.15)", "width": 1},
            },
            link={
                "source": [node_index[source] for source, _, _ in links],
                "target": [node_index[target] for _, target, _ in links],
                "value": [value for _, _, value in links],
                "color": ["rgba(87,227,178,.16)" if target in {"Anthropic", "OpenAI", "Hyperscalers"} else "rgba(96,165,250,.14)" for _, target, _ in links],
            },
        )
    )
    figure.update_layout(
        height=540,
        margin=dict(l=12, r=12, t=20, b=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#cbd5e1", size=12, family="Inter, Arial"),
    )
    return figure

