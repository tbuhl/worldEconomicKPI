# World KPI Radar

World KPI Radar is a live Streamlit dashboard for monitoring global economic vulnerability, present-tense financial stress, U.S. sovereign financing pressure, and the AI infrastructure capital cycle.

It is built to answer a more useful question than “when will the economy collapse?”:

> Which fragilities are historically stretched, which are actively transmitting stress, and how broad is the deterioration?

The app currently assembles roughly 58 usable KPIs from 43 FRED series, daily market data, U.S. Treasury data, Treasury International Capital holdings, and SEC company facts. Provider failures are isolated, and the last successful downloads remain available in a local cache.

## Run it

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

Streamlit prints the local URL, normally `http://localhost:8501`.

For responsible SEC access, you may identify yourself with:

```powershell
$env:WORLD_KPI_USER_AGENT = "WorldKPI your-email@example.com"
streamlit run app.py
```

Charts default to **Since 1990**, so the dot-com peak, the 2007 credit-cycle turn and Lehman are visible whenever the underlying series existed. The sidebar can narrow the view to 20, 10 or 5 years.

The sidebar’s **Refresh all sources** button preserves `.world_kpi_cache/` history. FRED and market feeds download only a recent overlap, merge revisions and append new observations. Daily refresh does not make monthly or quarterly releases update daily; every KPI shows its own observation date and frequency.

For server deployments, mount `.world_kpi_cache/` on persistent storage. That allows the long archive to be collected once and survive restarts or new application versions. A stateless server will rebuild the archive after a new instance starts.

## What is included

- **Growth and labour:** Sahm rule, unemployment, jobless claims, payrolls, job openings, real GDP, industrial production, retail sales, sentiment, permits and a recession-probability cross-check.
- **Inflation and policy:** headline/core CPI, core PCE, the effective funds rate, real yields, inflation expectations and mortgage rates.
- **Sovereign and rates:** the U.S. curve, term premium, debt/GDP, federal interest-cost growth, daily debt outstanding, JGB yields, USD/JPY, and the five largest current foreign Treasury holders. The TIC monitor separates holdings changes from reported monthly net flows and flags whether selling is unusual for each country.
- **Credit and plumbing:** high-yield and investment-grade spreads, two financial-stress indexes, bank lending standards, delinquencies and bank-loan growth.
- **Markets and global transmission:** VIX, dollar, oil, copper, policy uncertainty, ECB policy and derived equity drawdown/volatility.
- **AI capital cycle:** technology leadership, market breadth, semiconductors, an equal-weight AI equity basket, hyperscaler capex, capex growth, capex/cash flow, capex/revenue, and NVIDIA inventory and receivables growth.
- **AI capital loop:** a source-linked relationship ledger for investments, compute purchases, capacity commitments and conditional warrants. The different forms of disclosed value are deliberately not summed.

## Scoring method

1. Each raw series is converted to a meaningful level or year-over-year rate.
2. The latest observation is ranked against its own available history, generally beginning in 1990.
3. The percentile is oriented by its adverse direction. For example, high credit spreads are adverse, while low payroll growth is adverse. Oil, FX and similar shock variables are treated as two-sided.
4. KPIs are weighted within a pillar. Pillars are then equal-weighted into the **Broad Pressure Index**, preventing a pillar with more available series from dominating.
5. Dot-com and GFC dates are replayed using the same lens and only indicators available at those dates.

The score is a measure of historical stretch, **not a probability of recession or market loss**. A reading of 80/100 does not mean an 80% chance of a crash.

## Primary data sources

- [FRED](https://fred.stlouisfed.org/) for macroeconomic, rate and credit time series.
- [U.S. Treasury Fiscal Data: Debt to the Penny](https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/) for daily federal debt.
- [U.S. Treasury TIC](https://home.treasury.gov/data/treasury-international-capital-tic-system/) for reported foreign Treasury holdings and net purchases/sales. The top five are selected dynamically from the latest country rows, and each sale is ranked against that country's available monthly history. TIC warns that custody location can obscure beneficial ownership.
- [SEC company facts](https://www.sec.gov/edgar/sec-api-documentation) for annual cash capex, operating cash flow, revenue, inventory and receivables.
- [Yahoo Finance](https://finance.yahoo.com/markets/) chart data for transparent price-derived ETF and equity signals.
- [Federal Reserve Financial Stability Report](https://www.federalreserve.gov/publications/financial-stability-report.htm) for the four-part vulnerability framework: valuations, borrowing, financial leverage and funding risk.
- [BIS debt service ratios](https://data.bis.org/topics/DSR) for the research basis behind debt-service and credit-cycle monitoring. BIS emphasizes comparing a country with its own history rather than comparing raw DSR levels across countries.

The AI relationship ledger links directly to primary announcements and filings, including [OpenAI’s Stargate announcement](https://openai.com/index/announcing-the-stargate-project/), [NVIDIA’s OpenAI partnership](https://nvidianews.nvidia.com/news/openai-and-nvidia-announce-strategic-partnership-to-deploy-10gw-of-nvidia-systems), [Amazon’s Anthropic announcement](https://www.aboutamazon.com/news/company-news/amazon-invests-additional-5-billion-anthropic-ai), and [AMD’s filed warrant terms](https://ir.amd.com/financial-information/sec-filings/content/0001193125-25-230895/0001193125-25-230895.pdf).

## Important limitations

- Historical FRED comparisons use today’s revised series, not the data vintage investors saw at the time.
- Fiscal year-ends differ across SEC filers. Amazon’s finance-lease equipment is not fully represented in cash PP&E, so company comparisons are directional.
- Market prices are fast but noisy; GDP, delinquencies, TIC holdings and filings are slower and arrive with lags.
- Percentiles do not know that regimes change. A structurally higher debt ratio will naturally sit high in history, which is why the app pairs debt stocks with interest costs, rates and market stress.
- Free public endpoints can change. Source failures are shown in the **KPI library** rather than silently replaced.

## Tests

```powershell
pytest
python -m compileall -q app.py world_kpi
```

The unit suite checks percentile orientation, two-sided risks, release-frequency transforms, equal pillar weighting, SEC concept transitions, persistent incremental merges and crisis markers.
